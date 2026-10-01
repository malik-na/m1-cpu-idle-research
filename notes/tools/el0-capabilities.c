// Read-only AArch64 EL0 capability probe for Apple Silicon macOS.
// Each potentially trapped MRS runs in a child with core dumps disabled.
// No register writes, WFI, MMIO, root privileges, or kernel changes.
#include <inttypes.h>
#include <mach/mach_time.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#define READ_REG(name) \
static __attribute__((noinline)) uint64_t read_##name(void) { \
    uint64_t v; \
    __asm__ volatile("isb\n\tmrs %0, " #name : "=r"(v) :: "memory"); \
    return v; \
}
READ_REG(cntvct_el0)
READ_REG(cntfrq_el0)
READ_REG(cntpct_el0)
READ_REG(tpidr_el0)
READ_REG(tpidrro_el0)
READ_REG(pmccntr_el0)
READ_REG(pmuserenr_el0)
READ_REG(mpidr_el1)
READ_REG(s3_5_c15_c5_0) // Apple CYC_OVRD

struct probe { const char *name; uint64_t (*read)(void); };
static const struct probe probes[] = {
    {"CNTVCT_EL0", read_cntvct_el0},
    {"CNTFRQ_EL0", read_cntfrq_el0},
    {"CNTPCT_EL0", read_cntpct_el0},
    {"TPIDR_EL0", read_tpidr_el0},
    {"TPIDRRO_EL0", read_tpidrro_el0},
    {"PMCCNTR_EL0", read_pmccntr_el0},
    {"PMUSERENR_EL0", read_pmuserenr_el0},
    {"MPIDR_EL1", read_mpidr_el1},
    {"CYC_OVRD", read_s3_5_c15_c5_0},
};

static void counter_triplet(uint64_t *v0, uint64_t *p, uint64_t *v1) {
    __asm__ volatile(
        "isb\n\tmrs %0, cntvct_el0\n\tmrs %1, cntpct_el0\n\tmrs %2, cntvct_el0"
        : "=r"(*v0), "=r"(*p), "=r"(*v1) :: "memory");
}

int main(void) {
    struct rlimit no_core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &no_core)) { perror("setrlimit"); return 1; }
    for (size_t i = 0; i < sizeof(probes)/sizeof(probes[0]); i++) {
        pid_t child = fork();
        if (child < 0) { perror("fork"); return 1; }
        if (!child) {
            uint64_t value = probes[i].read();
            if (i == 1) printf("%s: readable, frequency=%" PRIu64 " Hz\n", probes[i].name, value);
            else if (i == 3) printf("%s: readable, logical cluster=%u, CPU=%u\n", probes[i].name,
                                    (unsigned)((value >> 12) & 0xff), (unsigned)(value & 0xfff));
            else printf("%s: readable\n", probes[i].name);
            fflush(stdout);
            _exit(0);
        }
        int status;
        if (waitpid(child, &status, 0) < 0) { perror("waitpid"); return 1; }
        if (WIFSIGNALED(status)) printf("%s: trapped, signal=%d\n", probes[i].name, WTERMSIG(status));
        else if (!WIFEXITED(status) || WEXITSTATUS(status)) printf("%s: child exit/status=%d\n", probes[i].name, status);
        fflush(stdout);
    }
    mach_timebase_info_data_t tb;
    if (mach_timebase_info(&tb)) return 1;
    printf("Mach timebase: %u/%u ns per tick\n", tb.numer, tb.denom);
    unsigned mach_brackets = 0, physical_brackets = 0;
    uint64_t max_span = 0;
    for (unsigned i = 0; i < 10000; i++) {
        uint64_t m0 = mach_absolute_time(), v = read_cntvct_el0(), m1 = mach_absolute_time();
        mach_brackets += m0 <= v && v <= m1;
        uint64_t v0, p, v1;
        counter_triplet(&v0, &p, &v1);
        physical_brackets += v0 <= p && p <= v1;
        if (v1-v0 > max_span) max_span = v1-v0;
    }
    printf("CNTVCT within Mach bracket: %u/10000\n", mach_brackets);
    printf("CNTPCT within CNTVCT bracket: %u/10000; max CNTVCT span: %" PRIu64 " ticks\n",
           physical_brackets, max_span);
    return 0;
}
