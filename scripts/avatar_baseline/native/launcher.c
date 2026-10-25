#include <unistd.h>
#include <grp.h>
#include <stdio.h>
int main(int argc,char **argv) {
 if(argc<2 || chroot("/host") || chdir("/workspace/css-is") || setgroups(0,0) || setgid(1000) || setuid(1000)) {perror("avatar fixture setup");return 1;}
 execvp(argv[1],argv+1);perror("avatar fixture exec");return 1;
}
