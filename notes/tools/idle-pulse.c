// Bounded user-space workload. Does not modify CPU idle policy or hardware.
// Usage: idle-pulse background|user  seconds  period_us  busy_us
#include <mach/mach_time.h>
#include <pthread.h>
#include <sys/qos.h>
#include <time.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern uint64_t idle_burst(uint64_t ticks, uint64_t seed);

static uint64_t ns(void) { return clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW); }
static int compare(const void *a, const void *b) {
    uint64_t x=*(const uint64_t *)a, y=*(const uint64_t *)b;
    return (x>y)-(x<y);
}
int main(int argc, char **argv) {
    if (argc!=5 || (strcmp(argv[1],"background") && strcmp(argv[1],"user"))) return 2;
    double seconds=atof(argv[2]);
    uint64_t period_us=strtoull(argv[3],NULL,10), busy_us=strtoull(argv[4],NULL,10);
    if (seconds<1 || seconds>30 || period_us<1000 || period_us>1000000 || busy_us>period_us/2 || !busy_us) return 2;
    qos_class_t qos=!strcmp(argv[1],"background")?QOS_CLASS_BACKGROUND:QOS_CLASS_USER_INITIATED;
    int ret=pthread_set_qos_class_self_np(qos,0);
    if (ret) { fprintf(stderr,"QoS failed: %d\n",ret); return 3; }
    mach_timebase_info_data_t tb; mach_timebase_info(&tb);
    uint64_t period_ns=period_us*1000, busy_ns=busy_us*1000;
    uint64_t start=ns(), start_mach=mach_absolute_time(), deadline=start+(uint64_t)(seconds*1e9);
    uint64_t busy_total=0,n=0,skipped=0,slot=1;
    uint64_t lates[31000];
    uint64_t seed=1;
    while (ns()<deadline && n<31000) {
        uint64_t before=ns();
        seed=idle_burst((uint64_t)((__uint128_t)busy_ns*tb.denom/tb.numer),seed);
        busy_total+=ns()-before;
        n++;
        uint64_t target=start+slot*period_ns;
        uint64_t absolute_target=start_mach+(uint64_t)((__uint128_t)(slot*period_ns)*tb.denom/tb.numer);
        mach_wait_until(absolute_target);
        uint64_t wake=ns(); lates[n-1]=wake>target?wake-target:0;
        uint64_t next_slot=(wake-start)/period_ns+1;
        if (next_slot>slot+1) skipped+=next_slot-slot-1;
        slot=next_slot>slot?next_slot:slot+1;
    }
    double elapsed=(ns()-start)/1e9;
    qsort(lates,n,sizeof(uint64_t),compare);
    printf("{\"qos\":\"%s\",\"requested_seconds\":%.3f,\"elapsed_s\":%.9f,\"start_monotonic_s\":%.9f,\"period_us\":%llu,\"busy_us\":%llu,\"busy_observed_s\":%.9f,\"bursts\":%llu,\"missed_deadlines\":%llu,\"timer_lateness_p50_us\":%.3f,\"timer_lateness_p95_us\":%.3f,\"timer_lateness_max_us\":%.3f,\"checksum\":%llu}\n",argv[1],seconds,elapsed,start/1e9,period_us,busy_us,busy_total/1e9,n,skipped,lates[n/2]/1000.0,lates[(n-1)*95/100]/1000.0,lates[n-1]/1000.0,seed);
    return 0;
}
