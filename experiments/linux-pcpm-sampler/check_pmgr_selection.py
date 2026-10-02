#!/usr/bin/env python3
"""Exercise the patch's actual PMGR selector with source-derived T8103 banks.

This is a host-only source check. It never reads PMGR hardware or starts a
kernel capture. Optional full DTS paths verify the compact public fixtures
against immutable upstream source bytes before the C harness runs.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "pmgr-node-fixtures.json"
PATCH = HERE / "0001-t8103-pcpm-sampler.patch"
NODE_RE = re.compile(r"\b(pmgr(?:_mini)?):\s*power-management@[0-9a-f]+\s*\{([^{}]*)\};", re.S)


def dts_nodes(source: str) -> list[dict]:
    nodes = []
    for label, body in NODE_RE.findall(source):
        compatible = re.search(r"\bcompatible\s*=\s*([^;]+);", body)
        reg = re.search(r"\breg\s*=\s*<([^>]+)>\s*;", body)
        if not compatible or not reg:
            raise ValueError(f"{label}: missing compatible or reg")
        cells = [int(cell, 0) for cell in reg.group(1).split()]
        if len(cells) != 4:
            raise ValueError(f"{label}: expected four 32-bit reg cells")
        nodes.append({
            "label": label,
            "base": hex((cells[0] << 32) | cells[1]),
            "size": hex((cells[2] << 32) | cells[3]),
            "compatible": re.findall(r'"([^"]+)"', compatible.group(1)),
        })
    return nodes


def verify_dts(path: Path, fixture: dict) -> None:
    data = path.read_bytes()
    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash != fixture["full_dts_sha256"]:
        raise ValueError(f"{path}: full DTS SHA-256 mismatch: {actual_hash}")
    actual_nodes = dts_nodes(data.decode("utf-8"))
    if actual_nodes != fixture["nodes"]:
        raise ValueError(f"{path}: extracted PMGR nodes differ from fixture")


def patch_function() -> str:
    lines = PATCH.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("@@ -0,0 +1,"))
    added = lines[start + 1:]
    if not added or any(not line.startswith("+") for line in added):
        raise ValueError("expected one complete added C source in patch")
    source = "\n".join(line[1:] for line in added)
    marker = "static int qualify_regmap(void)"
    begin = source.index(marker)
    opening = source.index("{", begin)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[begin:i + 1]
    raise ValueError("unterminated qualify_regmap function")


HARNESS = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
#define ENODEV 19
#define EPROBE_DEFER 517
#define PCPM_PMGR_BASE UINT64_C(0x23b700000)
#define PCPM_PMGR_SIZE UINT64_C(0x14000)
#define ERR_PTR(e) ((struct regmap *)(intptr_t)(e))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))

struct resource { uint64_t start, end; };
#define resource_size(r) ((r)->end - (r)->start + 1)
struct regmap { int stride, val_bytes; };
struct node_spec { uint64_t base, size; int available, syscon, simple, map; };
struct device_node { struct node_spec spec; int id, refs; };
struct test_case {
    const char *name;
    struct node_spec nodes[3];
    int count, expected_ret, expected_mapped_id;
};
static struct device_node nodes[3];
static int node_count, mapped_id;
static struct regmap map = {4, 4};
static struct regmap *pcpm_map;
static uint64_t pmgr_phys, pmgr_size;
static int regmap_existing, regmap_internal_clockless;
static int regmap_stride, regmap_val_bytes;

static struct device_node *of_node_get(struct device_node *np)
{
    if (np) np->refs++;
    return np;
}
static void of_node_put(struct device_node *np)
{
    if (np && --np->refs < 0) abort();
}
static struct device_node *of_find_compatible_node(struct device_node *from,
                                                   const char *type,
                                                   const char *compatible)
{
    int next = from ? from->id + 1 : 0;
    (void)type;
    if (strcmp(compatible, "apple,t8103-pmgr")) abort();
    of_node_put(from); /* Linux drops the previous iterator reference. */
    if (next >= node_count) return NULL;
    return of_node_get(&nodes[next]);
}
static int of_address_to_resource(struct device_node *np, int index,
                                  struct resource *res)
{
    if (index || !np->spec.size) return -ENODEV;
    res->start = np->spec.base;
    res->end = np->spec.base + np->spec.size - 1;
    return 0;
}
static int of_device_is_available(struct device_node *np)
{ return np->spec.available; }
static int of_device_is_compatible(struct device_node *np, const char *name)
{
    if (!strcmp(name, "syscon")) return np->spec.syscon;
    if (!strcmp(name, "simple-mfd")) return np->spec.simple;
    abort();
}
static const void *of_find_property(struct device_node *np, const char *name,
                                    void *len)
{ (void)np; (void)name; (void)len; return NULL; }
static int of_property_count_u32_elems(struct device_node *np, const char *name)
{ (void)np; (void)name; return 1; }
static int of_property_read_u32(struct device_node *np, const char *name, u32 *value)
{ (void)np; (void)name; *value = 4; return 0; }
static struct regmap *syscon_node_to_existing_clockless_regmap(struct device_node *np)
{
    if (!np->spec.map) return ERR_PTR(-EPROBE_DEFER);
    mapped_id = np->id;
    return &map;
}
static int regmap_get_reg_stride(struct regmap *m) { return m->stride; }
static int regmap_get_val_bytes(struct regmap *m) { return m->val_bytes; }

__FUNCTION__

static const struct test_case cases[] = {
__CASES__
};
int main(void)
{
    size_t i;
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        const struct test_case *c = &cases[i];
        int j, actual;
        memset(nodes, 0, sizeof(nodes));
        node_count = c->count;
        mapped_id = -1;
        pcpm_map = NULL;
        pmgr_phys = pmgr_size = 0;
        regmap_existing = regmap_internal_clockless = 0;
        regmap_stride = regmap_val_bytes = 0;
        for (j = 0; j < node_count; j++) {
            nodes[j].spec = c->nodes[j];
            nodes[j].id = j;
        }
        actual = qualify_regmap();
        if (actual != c->expected_ret || mapped_id != c->expected_mapped_id) {
            fprintf(stderr, "%s: returned %d/map %d, expected %d/map %d\n",
                    c->name, actual, mapped_id,
                    c->expected_ret, c->expected_mapped_id);
            return 1;
        }
        for (j = 0; j < node_count; j++)
            if (nodes[j].refs) {
                fprintf(stderr, "%s: node %d leaked %d references\n",
                        c->name, j, nodes[j].refs);
                return 1;
            }
    }
    printf("%zu source-derived/negative selector cases passed\n",
           sizeof(cases) / sizeof(cases[0]));
    return 0;
}
'''


def c_node(node: dict, *, available: int = 1, syscon: int = 1,
           simple: int = 1, map_present: int = 1) -> str:
    assert "apple,t8103-pmgr" in node["compatible"]
    return "{" + ", ".join([
        node["base"] + "ULL", node["size"] + "ULL",
        str(available), str(syscon), str(simple), str(map_present),
    ]) + "}"


def make_cases(fixtures: dict) -> str:
    cases = []
    for source_name, source in fixtures["sources"].items():
        banks = source["nodes"]
        if len(banks) != 2 or [b["label"] for b in banks] != ["pmgr", "pmgr_mini"]:
            raise ValueError(f"{source_name}: unexpected PMGR bank fixture")
        main, mini = banks
        if (main["base"], main["size"]) != ("0x23b700000", "0x14000"):
            raise ValueError(f"{source_name}: target resource changed")

        def add(name: str, nodes: list[str], result: int, mapped: int) -> None:
            cases.append("    {" + ", ".join([
                json.dumps(f"{source_name}-{name}"),
                "{" + ", ".join(nodes) + "}",
                str(len(nodes)), str(result), str(mapped),
            ]) + "},")

        add("source-order", [c_node(main), c_node(mini)], 0, 0)
        add("reverse-order", [c_node(mini), c_node(main)], 0, 1)
        add("mini-only", [c_node(mini)], -19, -1)
        add("duplicate-main", [c_node(main), c_node(main), c_node(mini)], -19, -1)
        add("unavailable-main", [c_node(main, available=0), c_node(mini)], -19, -1)
        add("non-syscon-main", [c_node(main, syscon=0), c_node(mini)], -19, -1)
        add("missing-map", [c_node(main, map_present=0), c_node(mini)], -517, -1)
    return "\n".join(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asahi-dts", type=Path, help="full pinned Asahi t8103.dtsi")
    parser.add_argument("--aurora-dts", type=Path, help="full pinned Aurora t8103.dtsi")
    args = parser.parse_args()
    fixtures = json.loads(FIXTURES.read_text())
    for name in ("asahi", "aurora"):
        source_path = getattr(args, name + "_dts")
        if source_path:
            verify_dts(source_path, fixtures["sources"][name])
            print(f"{name}: full DTS digest and extracted PMGR banks match")

    code = HARNESS.replace("__FUNCTION__", patch_function()).replace(
        "__CASES__", make_cases(fixtures))
    with tempfile.TemporaryDirectory(prefix="pcpm-node-check-") as temp:
        source = Path(temp) / "check.c"
        binary = Path(temp) / "check"
        source.write_text(code)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
                        "-fsanitize=address,undefined", str(source), "-o", str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
