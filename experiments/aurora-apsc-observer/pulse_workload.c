#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* Fixed completed work per pulse; normal userspace CPU activity only. */
#define PULSES 44
#define ITERATIONS 1048576
#define PERIOD_NS UINT64_C(50000000)

struct sample { uint64_t start, end, value; int before, after; };

static uint64_t now(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(1); }
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static void until(uint64_t ns)
{
    struct timespec t = { .tv_sec = (time_t)(ns / UINT64_C(1000000000)),
                          .tv_nsec = (long)(ns % UINT64_C(1000000000)) };
    int error;
    do { error = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &t, NULL); }
    while (error == EINTR);
    if (error) { errno = error; perror("clock_nanosleep"); exit(1); }
}

int main(int argc, char **argv)
{
    char *end;
    if (argc != 3) { fprintf(stderr, "usage: pulse_workload CPU START_MONOTONIC_NS\n"); return 2; }
    errno = 0;
    long cpu = strtol(argv[1], &end, 10);
    if (errno || !*argv[1] || *end || cpu < 0 || cpu > 7) return 2;
    errno = 0;
    uint64_t start = strtoull(argv[2], &end, 10);
    if (errno || !*argv[2] || *end || argv[2][0] == '-' || start < now()) return 2;
    cpu_set_t affinity;
    CPU_ZERO(&affinity); CPU_SET((int)cpu, &affinity);
    if (sched_setaffinity(0, sizeof(affinity), &affinity)) { perror("sched_setaffinity"); return 1; }
    struct sample samples[PULSES];
    uint64_t x = UINT64_C(0x9e3779b97f4a7c15);
    for (unsigned int pulse = 0; pulse < PULSES; pulse++) {
        until(start + PERIOD_NS * pulse);
        samples[pulse].before = sched_getcpu(); samples[pulse].start = now();
        for (unsigned int i = 0; i < ITERATIONS; i++) { x ^= x << 13; x ^= x >> 7; x ^= x << 17; }
        samples[pulse].end = now(); samples[pulse].after = sched_getcpu(); samples[pulse].value = x;
        if (samples[pulse].before != cpu || samples[pulse].after != cpu) return 1;
    }
    until(start + PERIOD_NS * PULSES);
    /* Collector releases export only after the actual capture has drained. */
    int release = getchar();
    if (release != 'E' && release != EOF) return 2;
    puts("cpu,pulse,iterations,start_monotonic_ns,end_monotonic_ns,checksum");
    for (unsigned int pulse = 0; pulse < PULSES; pulse++)
        printf("%ld,%u,%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n", cpu, pulse, ITERATIONS,
               samples[pulse].start, samples[pulse].end, samples[pulse].value);
    return 0;
}
