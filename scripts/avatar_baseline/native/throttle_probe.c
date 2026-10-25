/* Diagnostic only: measure Chromium's original SIGUSR2 handler unchanged.
 * File-backed records survive Chromium's _exit. No handler time is subtracted
 * from acceptance measurements. Compile with gcc -shared -fPIC -ldl. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#define CAPACITY 262144
struct record { uint64_t start_ns, end_ns; };
struct buffer { uint64_t count, overflow; struct record records[CAPACITY]; };
static struct buffer *buffer;
static void (*original)(int);
static int (*real_sigaction)(int,const struct sigaction *,struct sigaction *);
static uint64_t monotonic_ns(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }
static void measure_handler(int sig) {
  int saved=errno;
  uint64_t begin=monotonic_ns();
  original(sig);
  uint64_t end=monotonic_ns();
  if(buffer) {
    uint64_t n=buffer->count;
    if(n<CAPACITY) {buffer->records[n]=(struct record){begin,end};buffer->count=n+1;}
    else buffer->overflow++;
  }
  errno=saved;
}
int sigaction(int sig,const struct sigaction *action,struct sigaction *old) {
  if(!real_sigaction) real_sigaction=dlsym(RTLD_NEXT,"sigaction");
  if(sig!=SIGUSR2 || !action || (action->sa_flags&SA_SIGINFO) || action->sa_handler==SIG_DFL || action->sa_handler==SIG_IGN)
    return real_sigaction(sig,action,old);
  if(!buffer) {
    const char *folder=getenv("AVATAR_SIGNAL_DIR");
    if(!folder) return real_sigaction(sig,action,old);
    char path[4096];snprintf(path,sizeof(path),"%s/%d.bin",folder,getpid());
    int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0600);
    if(fd<0) return real_sigaction(sig,action,old);
    if(ftruncate(fd,sizeof(struct buffer))==0) {
      void *p=mmap(NULL,sizeof(struct buffer),PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
      if(p!=MAP_FAILED) buffer=p;
    }
    close(fd);
  }
  if(!buffer) return real_sigaction(sig,action,old);
  original=action->sa_handler;
  struct sigaction copy=*action;copy.sa_handler=measure_handler;
  return real_sigaction(sig,&copy,old);
}
