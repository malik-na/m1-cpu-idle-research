// Read-only IOReport observation. No SMC writes, register writes, or power policy calls.
// Private ABI declarations cross-checked with macmon/OSHI and Xcode libIOReport.tbd.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach_time.h>
#include <unistd.h>
#include <stdint.h>

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
static NSString *s(CFStringRef r){return r ? (__bridge NSString*)r : @"";}
static id safe(id obj) {
 if([obj isKindOfClass:NSData.class]) return @{ @"base64":[obj base64EncodedStringWithOptions:0] };
 if([obj isKindOfClass:NSArray.class]){NSMutableArray *a=[NSMutableArray new];for(id x in obj)[a addObject:safe(x)];return a;}
 if([obj isKindOfClass:NSDictionary.class]){NSMutableDictionary*d=[NSMutableDictionary new];for(id k in obj)d[[k description]]=safe(obj[k]);return d;}
 if([obj isKindOfClass:NSString.class] || [obj isKindOfClass:NSNumber.class] || [obj isKindOfClass:NSNull.class]) return obj;
 return [obj description];
}
static NSArray *decode(CFDictionaryRef dict,BOOL values){
 NSArray *channels=((__bridge NSDictionary*)dict)[@"IOReportChannels"];
 NSMutableArray *out=[NSMutableArray new];
 for(NSDictionary *item in channels){
  CFDictionaryRef c=(__bridge CFDictionaryRef)item;
  int f=IOReportChannelGetFormat(c);
  NSMutableDictionary *d=[@{@"group":s(IOReportChannelGetGroup(c)),@"subgroup":s(IOReportChannelGetSubGroup(c)),@"name":s(IOReportChannelGetChannelName(c)),@"driver":s(IOReportChannelGetDriverName(c)),@"driver_id":@(IOReportChannelGetDriverID(c)),@"channel_id":@(IOReportChannelGetChannelID(c)),@"format":@(f),@"unit":s(IOReportChannelGetUnitLabel(c)),@"unit_code":@(IOReportChannelGetUnit(c))} mutableCopy];
  if(values && f==1)d[@"value"]=@(IOReportSimpleGetIntegerValue(c,NULL));
  if(values && f==2){
   int n=IOReportStateGetCount(c);NSMutableArray *states=[NSMutableArray new];
   for(int i=0;i<n;i++)[states addObject:@{@"index":@(i),@"name":s(IOReportStateGetNameForIndex(c,i)),@"id":@(IOReportStateGetIDForIndex(c,i)),@"residency":@(IOReportStateGetResidency(c,i)),@"intransitions":@(IOReportStateGetInTransitions(c,i))}];
   d[@"states"]=states;
  }
  if(values && f!=1 && f!=2)d[@"raw"]=safe(item);
  [out addObject:d];
 }
 return out;
}
static void emit(id obj){NSError*e=nil;NSData*data=[NSJSONSerialization dataWithJSONObject:obj options:NSJSONWritingSortedKeys error:&e];if(!data){fprintf(stderr,"JSON: %s\n",e.description.UTF8String);exit(3);}fwrite(data.bytes,1,data.length,stdout);fputc('\n',stdout);fflush(stdout);}
static double now(void){return (double)clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)/1e9;}
int main(int argc,char **argv){@autoreleasepool{
 void*lib=dlopen("/usr/lib/libIOReport.dylib",RTLD_NOW|RTLD_LOCAL);if(!lib){fprintf(stderr,"dlopen: %s\n",dlerror());return 2;}
 LOAD(IOReportCopyAllChannels);LOAD(IOReportCopyChannelsInGroup);LOAD(IOReportCreateSubscription);LOAD(IOReportCreateSamples);LOAD(IOReportCreateSamplesDelta);LOAD(IOReportChannelGetGroup);LOAD(IOReportChannelGetSubGroup);LOAD(IOReportChannelGetChannelName);LOAD(IOReportChannelGetUnitLabel);LOAD(IOReportChannelGetDriverName);LOAD(IOReportChannelGetChannelID);LOAD(IOReportChannelGetDriverID);LOAD(IOReportChannelGetUnit);LOAD(IOReportChannelGetFormat);LOAD(IOReportSimpleGetIntegerValue);LOAD(IOReportStateGetCount);LOAD(IOReportStateGetNameForIndex);LOAD(IOReportStateGetResidency);LOAD(IOReportStateGetInTransitions);LOAD(IOReportStateGetIDForIndex);
 if(argc<2){fprintf(stderr,"Usage: %s inventory | GROUP_OR_@idle [COUNT=3] [INTERVAL_SECONDS=1] [SUBGROUP]\n",argv[0]);return 1;}
 if(strcmp(argv[1],"inventory")==0){CFDictionaryRef c=IOReportCopyAllChannels(0,0);if(!c){fprintf(stderr,"no channels\n");return 4;}emit(@{@"type":@"inventory",@"date":[NSDate.date description],@"uid":@(getuid()),@"channels":decode(c,NO)});CFRelease(c);return 0;}
 NSString*g=[NSString stringWithUTF8String:argv[1]];NSString*sg=argc>4?[NSString stringWithUTF8String:argv[4]]:nil;
 int count=argc>2?atoi(argv[2]):3;double interval=argc>3?atof(argv[3]):1.0;
 if(count<1||count>10000||interval<0.05||interval>60){fprintf(stderr,"invalid sample limits\n");return 1;}
 CFMutableDictionaryRef channels=NULL;
 if([g isEqualToString:@"@idle"]){
  CFDictionaryRef all=IOReportCopyAllChannels(0,0);
  if(all){
   channels=CFDictionaryCreateMutableCopy(kCFAllocatorDefault,0,all);
   NSArray* arr=((__bridge NSDictionary*)all)[@"IOReportChannels"];
   NSMutableArray* selected=[NSMutableArray new];
   for(NSDictionary* item in arr){
    CFDictionaryRef c=(__bridge CFDictionaryRef)item;
    NSString* cg=s(IOReportChannelGetGroup(c));NSString* csg=s(IOReportChannelGetSubGroup(c));NSString* cn=s(IOReportChannelGetChannelName(c));
    if([cg isEqualToString:@"CPU Stats"] || [cg isEqualToString:@"SoC Stats"] || ([cg isEqualToString:@"PMP"] && ([csg isEqualToString:@"IOP State"] || [csg isEqualToString:@"Power"] || ([csg isEqualToString:@"Energy Counters"] && ([cn isEqualToString:@"ECPU"] || [cn isEqualToString:@"PCPU"])))))[selected addObject:item];
   }
   CFDictionarySetValue(channels,CFSTR("IOReportChannels"),(__bridge CFArrayRef)selected);CFRelease(all);
  }
 }else channels=IOReportCopyChannelsInGroup((__bridge CFStringRef)g,(__bridge CFStringRef)sg,0,0,0);
 if(!channels){fprintf(stderr,"group not found\n");return 4;}
 emit(@{@"type":@"selected",@"date":[NSDate.date description],@"uid":@(getuid()),@"channels":decode(channels,NO)});
 CFMutableDictionaryRef subscribed=NULL;IOReportSubscriptionRef sub=IOReportCreateSubscription(NULL,channels,&subscribed,0,NULL);
 if(!sub||!subscribed){fprintf(stderr,"subscription failed (sub=%p channels=%p)\n",sub,subscribed);return 5;}
 CFDictionaryRef prev=IOReportCreateSamples(sub,subscribed,NULL);double tprev=now();if(!prev){fprintf(stderr,"initial sample failed\n");return 6;}
 emit(@{@"type":@"initial",@"date":[NSDate.date description],@"monotonic_s":@(tprev),@"channels":decode(prev,YES)});
 for(int i=0;i<count;i++){@autoreleasepool{
  usleep((useconds_t)(interval*1e6));CFDictionaryRef cur=IOReportCreateSamples(sub,subscribed,NULL);double tcur=now();if(!cur){fprintf(stderr,"sample failed\n");return 6;}
  CFDictionaryRef delta=IOReportCreateSamplesDelta(prev,cur,NULL);if(!delta){fprintf(stderr,"delta failed\n");return 7;}
  emit(@{@"type":@"delta",@"index":@(i),@"date":[NSDate.date description],@"monotonic_s":@(tcur),@"elapsed_s":@(tcur-tprev),@"channels":decode(delta,YES)});
  CFRelease(delta);CFRelease(prev);prev=cur;tprev=tcur;
 }}
 CFRelease(prev);
 // Private subscription ownership is undocumented; process exit closes subscription.
 return 0;
}}
