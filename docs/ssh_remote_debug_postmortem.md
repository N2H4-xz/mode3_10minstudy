# Codex 远程服务器 SSH 与部署排查复盘

本文复盘 2026-05-08 将本地修改部署到远程服务器 `118.190.201.47` 的排查过程。重点记录为什么重复尝试了很久、分别踩了什么坑、当时的排查思路，以及最后如何解决。

## 背景

本次目标不是单纯启动本地服务，而是把本地项目 `D:\project\voice\mode3_10minstudy` 中的改动部署到远程服务器。

涉及的改动包括：

- 学习风格对话调用时带上历史上下文。
- 学习风格答题开始后隐藏风格画像面板。
- 给旧的学习画像套用新版 prompt 规则。
- 补充对应后端测试。

远程服务器信息：

- 公网地址：`118.190.201.47`
- 远程用户：`admin`
- 远程项目目录：`/home/admin/mode3_10minstudy`
- 远程服务进程：`.venv/bin/python -m uvicorn web_app:app --host 0.0.0.0 --port 80`

## 时间线

### 1. 先误把服务启动在本机

最开始用户给出 `http://118.190.201.47/`，我先在当前工作环境里把服务从 `127.0.0.1:8010` 改为 `0.0.0.0:80`。

这个判断的问题是：当前 Codex shell 所在机器并不是 `118.190.201.47`，而是本机/当前工作环境。把服务绑定到 `0.0.0.0` 只会让当前机器对外监听，不会影响远程服务器。

当用户指出“本机不是 118.190.201.47，这是一个远程服务器，ssh 连接”后，才切换到 SSH 部署思路。

教训：看到公网 URL 时不能默认当前 shell 就在那台服务器上。必须先确认：

```bash
hostname
whoami
pwd
ip addr
```

或者通过 SSH 明确进入远程机器后再操作。

### 2. SSH 初次失败，被误判为公钥未放好

最初尝试了几个常见用户：

- `root`
- `ubuntu`
- `admin`
- `ecs-user`

都返回：

```text
Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password)
```

当时的合理判断是：本机公钥没有加入服务器对应用户的 `authorized_keys`，或者用户名不对。

用户确认用户名是 `admin`，并在服务器终端中创建了：

```bash
/home/admin/.ssh/authorized_keys
```

然后把本机 `C:\Users\32563\.ssh\id_rsa.pub` 追加进去。

但之后仍然失败。

### 3. 云防火墙方向也排查了，但不是根因

由于日志中出现两个来源 IP：

```text
100.104.30.220 Accepted publickey
58.194.169.184 Connection reset ... [preauth]
```

当时怀疑过云防火墙、安全组、堡垒机通道或来源 IP 限制。

用户截图显示云防火墙已放行：

- TCP 22：`0.0.0.0/0`
- TCP 80：`0.0.0.0/0`
- TCP 443：`0.0.0.0/0`
- TCP 8888：`0.0.0.0/0`

所以云控制台防火墙不是主要问题。

这个方向不是完全错误，因为不同来源 IP 的确可能触发不同安全策略。但本次后续证据显示，连接已经能到达 SSHD，问题发生在认证流程内部。

### 4. SSH verbose 输出被低估了

关键排查命令：

```powershell
ssh -vvv -i C:\Users\32563\.ssh\codex_118_ed25519 `
  -o IdentitiesOnly=yes `
  -o PreferredAuthentications=publickey `
  admin@118.190.201.47 "echo OK"
```

输出中有两个很重要的信号：

```text
Server accepts key
sign_and_send_pubkey: signing using ssh-ed25519
we did not send a packet, disable method
No more authentication methods to try.
Permission denied
```

一开始只看到 `Server accepts key` 和 `Permission denied`，容易误以为是服务器端在接受 key 之后又拒绝用户。真正关键的是：

```text
we did not send a packet
```

这说明客户端在私钥签名阶段没有真正把最终认证包发出去。

### 5. 最大坑：生成的新 Ed25519 私钥其实带了口令

为排除 RSA 兼容性问题，我生成了 Ed25519 key。但在 Windows PowerShell 中调用 `ssh-keygen -N ""` 时，参数处理不符合预期，生成出来的私钥是加密的。

后来检查私钥头部发现：

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
bcrypt
```

`bcrypt` 说明私钥有口令保护。

而 Codex 使用的是非交互 SSH：

```text
BatchMode=yes
```

非交互模式不能弹出口令输入，所以客户端无法用这把私钥完成签名认证，最终表现为：

```text
Server accepts key
we did not send a packet
Permission denied
```

这就是重复尝试很久的核心原因。

### 6. 解决方式：生成真正无口令的 Ed25519 私钥

由于 Windows 下 `ssh-keygen -N ""` 多次被 PowerShell/cmd 转义干扰，最后改用 Python `cryptography` 生成标准 OpenSSH 无口令私钥。

生成出的新公钥：

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvioy2lerUhZP2NsJfPO6yeCtfOM+sE+2WM26s0anzo codex-118-plain
```

指纹：

```text
SHA256:6toHgSnZxzu+krpHJOtGtKjj671+Na3eC+pJkrrNmY0
```

用户把这行追加到服务器：

```bash
cat >> /home/admin/.ssh/authorized_keys <<'EOF'
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvioy2lerUhZP2NsJfPO6yeCtfOM+sE+2WM26s0anzo codex-118-plain
EOF
chmod 700 /home/admin/.ssh
chmod 600 /home/admin/.ssh/authorized_keys
chown -R admin:admin /home/admin/.ssh
```

随后 SSH 成功：

```text
OK
/home/admin
admin
iZm5e3t81oxs5kw0vnxb49Z
```

### 7. 部署阶段又踩了几个 shell 细节坑

#### 7.1 远程没有 git

远程项目目录存在，但服务器没有安装 `git`：

```text
bash: git: command not found
```

所以不能依赖 `git status` 或 `git pull`，改成文件级备份和 `scp` 覆盖。

备份目录：

```text
/home/admin/mode3_10minstudy_backup_20260508_152722
```

#### 7.2 PowerShell 会解析远程 `$(date ...)`

第一次远程备份时写了类似：

```powershell
ssh admin@host "ts=$(date +%Y%m%d_%H%M%S) ..."
```

PowerShell 把 `$(date ...)` 当成本地表达式处理，导致报错。

修正方式：把远程命令放进 PowerShell 单引号字符串，避免本地插值：

```powershell
$remote = 'cd /home/admin/mode3_10minstudy && ts=$(date +%Y%m%d_%H%M%S) && ...'
ssh ... admin@118.190.201.47 $remote
```

#### 7.3 `pgrep` 的 pattern 被当成选项

第一次重启时 pattern 中包含 `-m uvicorn`，远程 `pgrep` 把 `-m` 当作自己的参数，报：

```text
pgrep: invalid option -- 'm'
```

修正方式：使用更简单的 pattern：

```bash
pgrep -f 'uvicorn web_app:app'
```

#### 7.4 远程脚本没有真正通过 stdin 传给 `bash -s`

第一次写了 `bash -s` 但没有把脚本内容管过去，命令等待 stdin 后超时。

修正方式：

```powershell
$remote | ssh ... admin@118.190.201.47 bash -s
```

### 8. 最终部署动作

同步文件：

```text
web_app.py
prompt_builder.py
static/app.js
tests/test_web_app_helpers.py
```

远程测试：

```bash
cd /home/admin/mode3_10minstudy
.venv/bin/python -m unittest tests.test_web_app_helpers
```

结果：

```text
Ran 12 tests
OK
```

重启服务：

```bash
cd /home/admin/mode3_10minstudy
pids=$(pgrep -f 'uvicorn web_app:app' || true)
if [ -n "$pids" ]; then
  kill $pids
  sleep 2
fi
nohup /home/admin/mode3_10minstudy/.venv/bin/python -m uvicorn web_app:app --host 0.0.0.0 --port 80 > /home/admin/mode3_10minstudy/uvicorn.log 2>&1 &
```

验证：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://118.190.201.47/"
Invoke-WebRequest -UseBasicParsing -Uri "http://118.190.201.47/static/app.js"
Invoke-WebRequest -UseBasicParsing -Uri "http://118.190.201.47/api/users"
```

公网返回 `200`，`static/app.js` 中确认包含新逻辑：

```text
learnedTurnsStarted
showProfilePanel
```

## 根因总结

真正拖慢排查的根因不是单一问题，而是多个问题叠加：

1. 一开始没有确认当前 shell 是否在远程服务器，误在本机启动过服务。
2. SSH 初始失败时只按“公钥没放好”排查，后续没有立刻抓完整 `-vvv` 关键行。
3. 服务器日志中存在另一个成功来源 IP，干扰了判断，让排查走向云防火墙/来源 IP。
4. Windows 下生成 key 时，空口令参数被错误处理，生成了加密私钥。
5. 非交互 SSH 无法输入私钥口令，导致 `Server accepts key` 之后仍失败。
6. PowerShell 与远程 shell 的转义规则不同，部署脚本中又遇到若干命令转义问题。

## 以后看到类似现象怎么快速判断

如果 `ssh -vvv` 中出现：

```text
Server accepts key
we did not send a packet
Permission denied
```

优先检查本地私钥是否带口令，而不是继续改服务器权限。

检查私钥：

```powershell
Get-Content -TotalCount 5 C:\Users\32563\.ssh\some_key
```

如果 OpenSSH 私钥正文附近能看到 `bcrypt`，通常表示私钥加密过。非交互 Codex 场景应换成无口令专用 key，或显式使用可用的 agent。

## 本次最终可用 SSH 命令

```powershell
$kh = Join-Path $env:TEMP 'codex_118_ssh_known_hosts'
ssh -i $env:USERPROFILE\.ssh\codex_118_plain_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  admin@118.190.201.47 "pwd && whoami && hostname"
```

