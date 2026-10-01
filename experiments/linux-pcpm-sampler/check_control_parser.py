#!/usr/bin/env python3
"""Compile the patch's actual pure command parser with narrow host API substitutes."""
from pathlib import Path
import os
import subprocess
import tempfile

PATCH = Path(__file__).with_name('0001-t8103-pcpm-sampler.patch')
MARKER = 'diff --git a/drivers/soc/apple/apple-pcpm-sampler.c '
HEADER = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define PCPM_MAX_SAMPLES 1000
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define check_mul_overflow(a,b,p) __builtin_mul_overflow(a,b,p)
#define check_add_overflow(a,b,p) __builtin_add_overflow(a,b,p)
/* The production parser checks digits first. Substitute only decimal u32 conversion. */
static int kstrtou32(const char *s, unsigned int base, u32 *out)
{
    char *end;
    unsigned long long value;
    errno = 0;
    value = strtoull(s, &end, base);
    if (errno || *end || value > UINT32_MAX) return -EINVAL;
    *out = (u32)value;
    return 0;
}
'''
TRAILER = r'''
struct test { const char *text; int ok; bool mmio; u32 count, period, phase; };
int main(void)
{
    const struct test tests[] = {
        {"mmio 50 100 0",1,true,50,100,0},
        {"records\t50\t100\t1\n",1,false,50,100,1},
        {"mmio 1000 10 0\n",1,true,1000,10,0},
        {"mmio 9 1000 999",1,true,9,1000,999},
        {"records 0001 0010 0000",1,false,1,10,0},
        {"mmio 1 10 9",1,true,1,10,9},
        {"mmio 1 10 10",0}, {"mmio 1000 10 1",0},
        {"mmio 0 10 0",0}, {"mmio 1001 10 0",0},
        {"mmio 1 9 0",0}, {"mmio 1 1001 0",0},
        {"mmio -4294967295 10 0",0}, {"mmio +1 10 0",0},
        {"mmio 4294967296 10 0",0}, {"mmio 18446744073709551616 10 0",0},
        {"mmio 1 10 -1",0}, {"mmio 1 1e2 0",0},
        {" mmio 1 10 0",0}, {"mmio 1 10 0 ",0},
        {"mmio  1 10 0",0}, {"mmio 1\t 10 0",0},
        {"mmio 1 10",0}, {"mmio 1 10 0 extra",0},
        {"mmio 1 10 0\n\n",0}, {"mmio 1 10 0\r\n",0},
        {"mmio\n1 10 0",0}, {"write 1 10 0",0}, {"",0},
        {"mmio 1 10 0\t",0}, {"mmio 1 10 0x0",0}
    };
    for (size_t i = 0; i < ARRAY_SIZE(tests); i++) {
        char *input = strdup(tests[i].text);
        bool mode = false;
        u32 count = 0, period = 0, phase = 0;
        int ret = parse_request(input, &mode, &count, &period, &phase);
        free(input);
        if ((!ret) != tests[i].ok || (!ret &&
            (mode != tests[i].mmio || count != tests[i].count ||
             period != tests[i].period || phase != tests[i].phase))) {
            fprintf(stderr, "parser case %zu failed\n", i);
            return 1;
        }
    }
    printf("Actual C parser: %zu boundary cases passed\n", ARRAY_SIZE(tests));
    return 0;
}
'''


def main():
    part = PATCH.read_text().split(MARKER, 1)[1].split('\ndiff --git ', 1)[0]
    source = '\n'.join(line[1:] for line in part.splitlines()
                       if line.startswith('+') and not line.startswith('+++'))
    parser = source[source.index('static int parse_request('):
                    source.index('\nstatic ssize_t control_write(')]
    with tempfile.TemporaryDirectory(prefix='pcpm-parser-') as directory:
        source_path = Path(directory) / 'parser.c'
        binary = Path(directory) / 'parser'
        source_path.write_text(HEADER + parser + TRAILER)
        subprocess.run([os.environ.get('CC', 'clang'), '-std=gnu11', '-Wall', '-Wextra',
                        '-Werror', '-Wno-missing-field-initializers',
                        '-fsanitize=address,undefined', '-g', str(source_path),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
