
/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium:     file format elf64-x86-64


Disassembly of section .text:

00000000100cce80 <getaddrinfo@@Base+0x3127490>:
    100cce80:	f3 0f 1e fa          	endbr64
    100cce84:	55                   	push   %rbp
    100cce85:	48 89 e5             	mov    %rsp,%rbp
    100cce88:	41 57                	push   %r15
    100cce8a:	41 56                	push   %r14
    100cce8c:	53                   	push   %rbx
    100cce8d:	48 83 ec 18          	sub    $0x18,%rsp
    100cce91:	64 48 8b 04 25 28 00 	mov    %fs:0x28,%rax
    100cce98:	00 00 
    100cce9a:	48 89 45 e0          	mov    %rax,-0x20(%rbp)
    100cce9e:	83 7f 48 00          	cmpl   $0x0,0x48(%rdi)
    100ccea2:	0f 84 88 00 00 00    	je     100ccf30 <getaddrinfo@@Base+0x3127540>
    100ccea8:	48 89 f1             	mov    %rsi,%rcx
    100cceab:	48 89 fb             	mov    %rdi,%rbx
    100cceae:	48 c7 45 d8 00 00 00 	movq   $0x0,-0x28(%rbp)
    100cceb5:	00 
    100cceb6:	48 8d 35 83 a2 d2 03 	lea    0x3d2a283(%rip),%rsi        # 13df7140 <__bss_start@@Base+0x213140>
    100ccebd:	48 8d 7d d8          	lea    -0x28(%rbp),%rdi
    100ccec1:	e8 5a 43 02 00       	call   100f1220 <getaddrinfo@@Base+0x314b830>
    100ccec6:	48 63 43 48          	movslq 0x48(%rbx),%rax
    100cceca:	48 85 c0             	test   %rax,%rax
    100ccecd:	74 3b                	je     100ccf0a <getaddrinfo@@Base+0x312751a>
    100ccecf:	48 8b 75 d8          	mov    -0x28(%rbp),%rsi
    100cced3:	48 8d 0d 66 ea a4 03 	lea    0x3a4ea66(%rip),%rcx        # 13b1b940 <__data_start@@Base+0x2b940>
    100cceda:	48 c1 e0 03          	shl    $0x3,%rax
    100ccede:	48 23 01             	and    (%rcx),%rax
    100ccee1:	8b 00                	mov    (%rax),%eax
    100ccee3:	a9 00 00 00 40       	test   $0x40000000,%eax
    100ccee8:	0f 94 c1             	sete   %cl
    100cceeb:	b2 01                	mov    $0x1,%dl
    100cceed:	48 3b 35 8c 85 d8 03 	cmp    0x3d8858c(%rip),%rsi        # 13e55480 <__bss_start@@Base+0x271480>
    100ccef4:	0f 84 50 01 00 00    	je     100cd04a <getaddrinfo@@Base+0x312765a>
    100ccefa:	84 d2                	test   %dl,%dl
    100ccefc:	0f 84 52 01 00 00    	je     100cd054 <getaddrinfo@@Base+0x3127664>
    100ccf02:	85 c0                	test   %eax,%eax
    100ccf04:	0f 88 f5 00 00 00    	js     100ccfff <getaddrinfo@@Base+0x312760f>
    100ccf0a:	48 63 73 48          	movslq 0x48(%rbx),%rsi
    100ccf0e:	48 8d 05 2b ea a4 03 	lea    0x3a4ea2b(%rip),%rax        # 13b1b940 <__data_start@@Base+0x2b940>
    100ccf15:	48 c1 e6 03          	shl    $0x3,%rsi
    100ccf19:	48 23 30             	and    (%rax),%rsi
    100ccf1c:	8b 06                	mov    (%rsi),%eax
    100ccf1e:	74 18                	je     100ccf38 <getaddrinfo@@Base+0x3127548>
    100ccf20:	89 c1                	mov    %eax,%ecx
    100ccf22:	83 e1 01             	and    $0x1,%ecx
    100ccf25:	74 11                	je     100ccf38 <getaddrinfo@@Base+0x3127548>
    100ccf27:	8b 46 24             	mov    0x24(%rsi),%eax
    100ccf2a:	48 8b 76 18          	mov    0x18(%rsi),%rsi
    100ccf2e:	eb 13                	jmp    100ccf43 <getaddrinfo@@Base+0x3127553>
    100ccf30:	45 31 f6             	xor    %r14d,%r14d
    100ccf33:	e9 aa 00 00 00       	jmp    100ccfe2 <getaddrinfo@@Base+0x31275f2>
    100ccf38:	48 83 c6 18          	add    $0x18,%rsi
    100ccf3c:	d1 e8                	shr    $1,%eax
    100ccf3e:	25 ff ff ff 0f       	and    $0xfffffff,%eax
    100ccf43:	4c 8b 7d d8          	mov    -0x28(%rbp),%r15
    100ccf47:	85 c0                	test   %eax,%eax
    100ccf49:	74 55                	je     100ccfa0 <getaddrinfo@@Base+0x31275b0>
    100ccf4b:	89 c0                	mov    %eax,%eax
    100ccf4d:	45 31 f6             	xor    %r14d,%r14d
    100ccf50:	eb 17                	jmp    100ccf69 <getaddrinfo@@Base+0x3127579>
    100ccf52:	66 66 66 66 66 2e 0f 	data16 data16 data16 data16 cs nopw 0x0(%rax,%rax,1)
    100ccf59:	1f 84 00 00 00 00 00 
