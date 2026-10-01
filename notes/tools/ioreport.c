/* M1 IOReport observation-only collector, plain C, no Objective-C runtime.
 * Uses only report discovery/subscription/sample APIs. No power-control writes.
 * Private ABI: exported names verified in Xcode libIOReport.tbd; declarations
 * cross-checked against OSHI/macmon. Private ABI is not guaranteed by Apple.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef const void *IOReportSubscriptionRef;
#define FN(ret,name,args) static ret (*name) args
FN(CFMutableDictionaryRef,IOReportCopyAllChannels,(uint64_t,uint64_t));
FN(CFMutableDictionaryRef,IOReportCopyChannelsInGroup,(CFStringRef,CFStringRef,uint64_t,uint64_t,uint64_t));
FN(IOReportSubscriptionRef,IOReportCreateSubscription,(void*,CFMutableDictionaryRef,CFMutableDictionaryRef*,uint64_t,CFTypeRef));
FN(CFDictionaryRef,IOReportCreateSamples,(IOReportSubscriptionRef,CFMutableDictionaryRef,CFTypeRef));
FN(CFDictionaryRef,IOReportCreateSamplesDelta,(CFDictionaryRef,CFDictionaryRef,CFTypeRef));
FN(CFStringRef,IOReportChannelGetGroup,(CFDictionaryRef));
FN(CFStringRef,IOReportChannelGetSubGroup,(CFDictionaryRef));
FN(CFStringRef,IOReportChannelGetChannelName,(CFDictionaryRef));
FN(CFStringRef,IOReportChannelGetUnitLabel,(CFDictionaryRef));
FN(CFStringRef,IOReportChannelGetDriverName,(CFDictionaryRef));
FN(uint64_t,IOReportChannelGetChannelID,(CFDictionaryRef));
FN(uint64_t,IOReportChannelGetDriverID,(CFDictionaryRef));
FN(uint64_t,IOReportChannelGetUnit,(CFDictionaryRef));
FN(int,IOReportChannelGetFormat,(CFDictionaryRef));
FN(int64_t,IOReportSimpleGetIntegerValue,(CFDictionaryRef,void*));
FN(int,IOReportStateGetCount,(CFDictionaryRef));
FN(CFStringRef,IOReportStateGetNameForIndex,(CFDictionaryRef,int));
FN(int64_t,IOReportStateGetResidency,(CFDictionaryRef,int));
FN(int64_t,IOReportStateGetInTransitions,(CFDictionaryRef,int));
FN(uint64_t,IOReportStateGetIDForIndex,(CFDictionaryRef,int));
#define LOAD(n) do { *(void **)(&n)=dlsym(lib,#n); if(!n){fprintf(stderr,"missing %s\n",#n);return 2;} }while(0)
static void json_bytes(const uint8_t *p,size_t n){
 putchar('"');for(size_t i=0;i<n;i++)switch(p[i]){
 case '"':fputs("\\\"",stdout);break;case '\\':fputs("\\\\",stdout);break;
 case '\b':fputs("\\b",stdout);break;case '\f':fputs("\\f",stdout);break;
 case '\n':fputs("\\n",stdout);break;case '\r':fputs("\\r",stdout);break;case '\t':fputs("\\t",stdout);break;
 default:if(p[i]<32)printf("\\u%04x",p[i]);else putchar(p[i]);}
 putchar('"');
}
static void json_string(CFStringRef s){
 if(!s){fputs("\"\"",stdout);return;}
 CFIndex n=CFStringGetMaximumSizeForEncoding(CFStringGetLength(s),kCFStringEncodingUTF8)+1;
 char *p=malloc((size_t)n);if(!p){fprintf(stderr,"allocation failed\n");exit(3);}
 if(!CFStringGetCString(s,p,n,kCFStringEncodingUTF8)){free(p);fputs("null",stdout);return;}
 json_bytes((uint8_t*)p,strlen(p));free(p);
}
static int eq(CFStringRef a,CFStringRef b){return a && CFStringCompare(a,b,0)==kCFCompareEqualTo;}
static CFArrayRef channel_array(CFDictionaryRef d){return CFDictionaryGetValue(d,CFSTR("IOReportChannels"));}
static void decode(CFDictionaryRef d,int values){
 CFArrayRef arr=channel_array(d);putchar('[');
 CFIndex n=arr?CFArrayGetCount(arr):0;
 for(CFIndex j=0;j<n;j++){
  CFDictionaryRef c=CFArrayGetValueAtIndex(arr,j);int format=IOReportChannelGetFormat(c);if(j)putchar(',');
  fputs("{\"group\":",stdout);json_string(IOReportChannelGetGroup(c));
  fputs(",\"subgroup\":",stdout);json_string(IOReportChannelGetSubGroup(c));
  fputs(",\"name\":",stdout);json_string(IOReportChannelGetChannelName(c));
  fputs(",\"driver\":",stdout);json_string(IOReportChannelGetDriverName(c));
  printf(",\"driver_id\":%" PRIu64 ",\"channel_id\":%" PRIu64 ",\"format\":%d,\"unit\":",IOReportChannelGetDriverID(c),IOReportChannelGetChannelID(c),format);
  json_string(IOReportChannelGetUnitLabel(c));printf(",\"unit_code\":%" PRIu64,IOReportChannelGetUnit(c));
  if(values && format==1)printf(",\"value\":%" PRId64,IOReportSimpleGetIntegerValue(c,NULL));
  if(values && format==2){
   int count=IOReportStateGetCount(c);fputs(",\"states\":[",stdout);
   for(int i=0;i<count;i++){
    if(i)putchar(',');printf("{\"index\":%d,\"name\":",i);json_string(IOReportStateGetNameForIndex(c,i));
    printf(",\"id\":%" PRIu64 ",\"residency\":%" PRId64 ",\"intransitions\":%" PRId64 "}",IOReportStateGetIDForIndex(c,i),IOReportStateGetResidency(c,i),IOReportStateGetInTransitions(c,i));
   }putchar(']');
  }
  if(values && format!=1 && format!=2){
   CFErrorRef err=NULL;CFDataRef raw=CFPropertyListCreateData(kCFAllocatorDefault,c,kCFPropertyListXMLFormat_v1_0,0,&err);
   if(raw){fputs(",\"raw_plist\":",stdout);json_bytes(CFDataGetBytePtr(raw),(size_t)CFDataGetLength(raw));CFRelease(raw);}if(err)CFRelease(err);
  }putchar('}');
 }putchar(']');
}
static double now(void){return (double)clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)/1e9;}
static void record(const char *kind,int index,double monotonic,double elapsed,CFDictionaryRef d,int values){
 time_t wall=time(NULL);struct tm utc;gmtime_r(&wall,&utc);char date[32];strftime(date,sizeof(date),"%Y-%m-%dT%H:%M:%SZ",&utc);
 printf("{\"type\":\"%s\",\"date\":\"%s\",\"uid\":%u,\"collector\":\"plain-c-v1\"",kind,date,(unsigned)getuid());
 if(monotonic)printf(",\"monotonic_s\":%.9f",monotonic);
 if(index>=0)printf(",\"index\":%d,\"elapsed_s\":%.9f",index,elapsed);
 fputs(",\"channels\":",stdout);decode(d,values);fputs("}\n",stdout);fflush(stdout);
}
static CFMutableDictionaryRef idle_channels(void){
 CFDictionaryRef all=IOReportCopyAllChannels(0,0);if(!all)return NULL;
 CFMutableDictionaryRef out=CFDictionaryCreateMutableCopy(kCFAllocatorDefault,0,all);
 CFMutableArrayRef selected=CFArrayCreateMutable(kCFAllocatorDefault,0,&kCFTypeArrayCallBacks);
 CFArrayRef arr=channel_array(all);CFIndex n=arr?CFArrayGetCount(arr):0;
 for(CFIndex i=0;i<n;i++){
  CFDictionaryRef c=CFArrayGetValueAtIndex(arr,i);CFStringRef g=IOReportChannelGetGroup(c),s=IOReportChannelGetSubGroup(c),name=IOReportChannelGetChannelName(c);
  if(eq(g,CFSTR("CPU Stats"))||eq(g,CFSTR("SoC Stats"))||(eq(g,CFSTR("PMP"))&&(eq(s,CFSTR("IOP State"))||eq(s,CFSTR("Power"))||(eq(s,CFSTR("Energy Counters"))&&(eq(name,CFSTR("ECPU"))||eq(name,CFSTR("PCPU")))))))CFArrayAppendValue(selected,c);
 }
 CFDictionarySetValue(out,CFSTR("IOReportChannels"),selected);CFRelease(selected);CFRelease(all);return out;
}
int main(int argc,char **argv){
 setvbuf(stdout,NULL,_IOFBF,65536);
 void*lib=dlopen("/usr/lib/libIOReport.dylib",RTLD_NOW|RTLD_LOCAL);if(!lib){fprintf(stderr,"dlopen: %s\n",dlerror());return 2;}
 LOAD(IOReportCopyAllChannels);LOAD(IOReportCopyChannelsInGroup);LOAD(IOReportCreateSubscription);LOAD(IOReportCreateSamples);LOAD(IOReportCreateSamplesDelta);LOAD(IOReportChannelGetGroup);LOAD(IOReportChannelGetSubGroup);LOAD(IOReportChannelGetChannelName);LOAD(IOReportChannelGetUnitLabel);LOAD(IOReportChannelGetDriverName);LOAD(IOReportChannelGetChannelID);LOAD(IOReportChannelGetDriverID);LOAD(IOReportChannelGetUnit);LOAD(IOReportChannelGetFormat);LOAD(IOReportSimpleGetIntegerValue);LOAD(IOReportStateGetCount);LOAD(IOReportStateGetNameForIndex);LOAD(IOReportStateGetResidency);LOAD(IOReportStateGetInTransitions);LOAD(IOReportStateGetIDForIndex);
 if(argc<2){fprintf(stderr,"Usage: %s inventory | GROUP_OR_@idle [COUNT=3] [INTERVAL_SECONDS=1] [SUBGROUP]\n",argv[0]);return 1;}
 if(!strcmp(argv[1],"inventory")){CFDictionaryRef c=IOReportCopyAllChannels(0,0);if(!c){fprintf(stderr,"no channels\n");return 4;}record("inventory",-1,0,0,c,0);CFRelease(c);return 0;}
 char *end=NULL;long count=argc>2?strtol(argv[2],&end,10):3;if((argc>2&&(!end||*end))||count<1||count>10000){fprintf(stderr,"invalid count\n");return 1;}
 double interval=argc>3?strtod(argv[3],&end):1;if((argc>3&&(!end||*end))||!(interval>=0.05&&interval<=60)){fprintf(stderr,"invalid interval\n");return 1;}
 CFStringRef g=CFStringCreateWithCString(kCFAllocatorDefault,argv[1],kCFStringEncodingUTF8);
 CFStringRef sg=argc>4?CFStringCreateWithCString(kCFAllocatorDefault,argv[4],kCFStringEncodingUTF8):NULL;
 CFMutableDictionaryRef channels=!strcmp(argv[1],"@idle")?idle_channels():IOReportCopyChannelsInGroup(g,sg,0,0,0);
 CFRelease(g);if(sg)CFRelease(sg);if(!channels){fprintf(stderr,"group not found\n");return 4;}
 record("selected",-1,0,0,channels,0);
 CFMutableDictionaryRef subscribed=NULL;IOReportSubscriptionRef sub=IOReportCreateSubscription(NULL,channels,&subscribed,0,NULL);
 if(!sub||!subscribed){fprintf(stderr,"subscription failed (sub=%p channels=%p)\n",sub,(void*)subscribed);return 5;}
 CFDictionaryRef prev=IOReportCreateSamples(sub,subscribed,NULL);double tprev=now();if(!prev){fprintf(stderr,"initial sample failed\n");return 6;}
 record("initial",-1,tprev,0,prev,1);
 struct timespec delay={.tv_sec=(time_t)interval,.tv_nsec=(long)((interval-(time_t)interval)*1e9)};
 for(int i=0;i<count;i++){
  struct timespec remain=delay;while(nanosleep(&remain,&remain)<0){}
  CFDictionaryRef cur=IOReportCreateSamples(sub,subscribed,NULL);double tcur=now();if(!cur){fprintf(stderr,"sample failed\n");return 6;}
  CFDictionaryRef delta=IOReportCreateSamplesDelta(prev,cur,NULL);if(!delta){fprintf(stderr,"delta failed\n");return 7;}
  record("delta",i,tcur,tcur-tprev,delta,1);CFRelease(delta);CFRelease(prev);prev=cur;tprev=tcur;
 }
 CFRelease(prev);
 /* Process exit releases private subscription and its undocumented ownership. */
 return 0;
}
