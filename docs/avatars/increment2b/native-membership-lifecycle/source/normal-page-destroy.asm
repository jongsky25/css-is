
/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium:     file format elf64-x86-64


Disassembly of section .text:

0000000005aa4490 <ChromeMain@@Base+0x29189a0>:
     5aa4490:	f3 0f 1e fa          	endbr64
     5aa4494:	55                   	push   %rbp
     5aa4495:	48 89 e5             	mov    %rsp,%rbp
     5aa4498:	41 57                	push   %r15
     5aa449a:	41 56                	push   %r14
     5aa449c:	41 55                	push   %r13
     5aa449e:	41 54                	push   %r12
     5aa44a0:	53                   	push   %rbx
     5aa44a1:	50                   	push   %rax
     5aa44a2:	48 89 fb             	mov    %rdi,%rbx
     5aa44a5:	4c 8b 3f             	mov    (%rdi),%r15
     5aa44a8:	4c 8b 67 18          	mov    0x18(%rdi),%r12
     5aa44ac:	48 c7 47 18 00 00 00 	movq   $0x0,0x18(%rdi)
     5aa44b3:	00 
     5aa44b4:	4d 85 e4             	test   %r12,%r12
     5aa44b7:	74 44                	je     5aa44fd <ChromeMain@@Base+0x2918a0d>
     5aa44b9:	4d 8d 74 24 f8       	lea    -0x8(%r12),%r14
     5aa44be:	49 83 7c 24 f8 00    	cmpq   $0x0,-0x8(%r12)
     5aa44c4:	74 2f                	je     5aa44f5 <ChromeMain@@Base+0x2918a05>
     5aa44c6:	45 31 ed             	xor    %r13d,%r13d
     5aa44c9:	eb 0d                	jmp    5aa44d8 <ChromeMain@@Base+0x29189e8>
     5aa44cb:	0f 1f 44 00 00       	nopl   0x0(%rax,%rax,1)
     5aa44d0:	49 ff c5             	inc    %r13
     5aa44d3:	4d 3b 2e             	cmp    (%r14),%r13
     5aa44d6:	73 1d                	jae    5aa44f5 <ChromeMain@@Base+0x2918a05>
     5aa44d8:	4b 8b 3c ec          	mov    (%r12,%r13,8),%rdi
     5aa44dc:	4b c7 04 ec 00 00 00 	movq   $0x0,(%r12,%r13,8)
     5aa44e3:	00 
     5aa44e4:	48 85 ff             	test   %rdi,%rdi
     5aa44e7:	74 e7                	je     5aa44d0 <ChromeMain@@Base+0x29189e0>
     5aa44e9:	be 80 00 00 00       	mov    $0x80,%esi
     5aa44ee:	e8 cd fc 47 05       	call   af241c0 <_ZdaPvm@@Base>
     5aa44f3:	eb db                	jmp    5aa44d0 <ChromeMain@@Base+0x29189e0>
     5aa44f5:	4c 89 f7             	mov    %r14,%rdi
     5aa44f8:	e8 43 f7 47 05       	call   af23c40 <_ZdaPv@@Base>
     5aa44fd:	4d 8b 77 40          	mov    0x40(%r15),%r14
     5aa4501:	49 8b 7f 50          	mov    0x50(%r15),%rdi
     5aa4505:	be 00 00 02 00       	mov    $0x20000,%esi
     5aa450a:	e8 f1 03 01 00       	call   5ab4900 <ChromeMain@@Base+0x2928e10>
     5aa450f:	4c 89 f7             	mov    %r14,%rdi
     5aa4512:	48 89 de             	mov    %rbx,%rsi
     5aa4515:	48 83 c4 08          	add    $0x8,%rsp
     5aa4519:	5b                   	pop    %rbx
     5aa451a:	41 5c                	pop    %r12
     5aa451c:	41 5d                	pop    %r13
     5aa451e:	41 5e                	pop    %r14
     5aa4520:	41 5f                	pop    %r15
     5aa4522:	5d                   	pop    %rbp
     5aa4523:	e9 28 c0 00 00       	jmp    5ab0550 <ChromeMain@@Base+0x2924a60>
     5aa4528:	cc                   	int3
     5aa4529:	cc                   	int3
     5aa452a:	cc                   	int3
     5aa452b:	cc                   	int3
     5aa452c:	cc                   	int3
     5aa452d:	cc                   	int3
     5aa452e:	cc                   	int3
     5aa452f:	cc                   	int3
     5aa4530:	f3 0f 1e fa          	endbr64
     5aa4534:	80 7f 10 01          	cmpb   $0x1,0x10(%rdi)
     5aa4538:	75 1e                	jne    5aa4558 <ChromeMain@@Base+0x2918a68>
     5aa453a:	48 8d 4f 48          	lea    0x48(%rdi),%rcx
     5aa453e:	48 39 f1             	cmp    %rsi,%rcx
     5aa4541:	0f 87 bc 00 00 00    	ja     5aa4603 <ChromeMain@@Base+0x2918b13>
     5aa4547:	48 8b 57 38          	mov    0x38(%rdi),%rdx
     5aa454b:	48 01 ca             	add    %rcx,%rdx
     5aa454e:	31 c0                	xor    %eax,%eax
     5aa4550:	48 39 d6             	cmp    %rdx,%rsi
     5aa4553:	48 0f 42 c1          	cmovb  %rcx,%rax
     5aa4557:	c3                   	ret
     5aa4558:	48 8d 87 48 08 00 00 	lea    0x848(%rdi),%rax
     5aa455f:	48 39 f0             	cmp    %rsi,%rax
     5aa4562:	0f 97 c1             	seta   %cl
     5aa4565:	48 8d 97 00 00 02 00 	lea    0x20000(%rdi),%rdx
     5aa456c:	48 39 d6             	cmp    %rdx,%rsi
     5aa456f:	0f 93 c2             	setae  %dl
     5aa4572:	08 ca                	or     %cl,%dl
     5aa4574:	0f 85 89 00 00 00    	jne    5aa4603 <ChromeMain@@Base+0x2918b13>
     5aa457a:	89 f2                	mov    %esi,%edx
     5aa457c:	c1 ea 06             	shr    $0x6,%edx
     5aa457f:	81                   	.byte 0x81
