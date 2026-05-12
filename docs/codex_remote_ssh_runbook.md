# Codex 连接远程服务器操作手册

本文记录 Codex 从本地连接远程服务器、同步文件、重启服务的推荐流程，避免重复踩 SSH key、PowerShell 转义、远程进程重启等问题。

## 适用场景

当 Codex 当前 shell 不在目标服务器上，但需要部署到远程机器时，按本文流程操作。

示例服务器：

```text
host: 118.190.201.47
user: admin
project: /home/admin/mode3_10minstudy
service: .venv/bin/python -m uvicorn web_app:app --host 0.0.0.0 --port 80
```

## 先确认当前 shell 是否在远程

不要看到公网 URL 就默认当前 shell 是服务器。

本地执行：

```powershell
hostname
whoami
pwd
```

远程执行：

```powershell
ssh user@host "hostname && whoami && pwd"
```

只有 SSH 成功后，才认为已经进入远程部署流程。

## 推荐使用专用无口令 key

Codex 非交互执行 SSH 时，最好使用一把只用于该服务器的无口令 key。不要复用个人日常 key，也不要使用带口令私钥，除非已经配置可用的 ssh-agent。

### 方式一：用 Python 生成无口令 Ed25519 key

Windows PowerShell 中 `ssh-keygen -N ""` 容易被转义坑到。更稳的做法是用 Python 生成标准 OpenSSH 私钥。

```powershell
@'
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

key_path = Path.home() / ".ssh" / "codex_server_ed25519"
private_key = ed25519.Ed25519PrivateKey.generate()

private_bytes = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.OpenSSH,
    encryption_algorithm=serialization.NoEncryption(),
)
public_bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.OpenSSH,
    format=serialization.PublicFormat.OpenSSH,
) + b" codex-server\n"

key_path.write_bytes(private_bytes)
Path(str(key_path) + ".pub").write_bytes(public_bytes)
print(public_bytes.decode().strip())
'@ | python -
```

检查指纹：

```powershell
ssh-keygen -lf $env:USERPROFILE\.ssh\codex_server_ed25519.pub
```

检查私钥是否无口令：

```powershell
Get-Content -TotalCount 5 $env:USERPROFILE\.ssh\codex_server_ed25519
```

如果正文里出现 `bcrypt`，说明私钥被加密了，不适合非交互使用。

### 方式二：确认现有 key 可以非交互使用

```powershell
ssh -i $env:USERPROFILE\.ssh\some_key `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o BatchMode=yes `
  user@host "echo OK"
```

能返回 `OK` 才可用于 Codex 自动化。

## 把公钥加入服务器

在服务器终端执行：

```bash
mkdir -p /home/admin/.ssh
cat >> /home/admin/.ssh/authorized_keys <<'EOF'
粘贴 .pub 文件里的整行公钥
EOF
chmod 700 /home/admin/.ssh
chmod 600 /home/admin/.ssh/authorized_keys
chown -R admin:admin /home/admin/.ssh
```

确认用户存在：

```bash
id admin
```

确认文件：

```bash
ls -ld /home/admin /home/admin/.ssh
ls -l /home/admin/.ssh/authorized_keys
tail -n 3 /home/admin/.ssh/authorized_keys
```

## SSH 连接命令模板

建议用临时 known_hosts，避免污染或破坏用户正式 SSH 配置。

```powershell
$kh = Join-Path $env:TEMP 'codex_server_known_hosts'
ssh -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o PreferredAuthentications=publickey `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  -o BatchMode=yes `
  admin@118.190.201.47 "echo OK && pwd && whoami && hostname"
```

成功输出应类似：

```text
OK
/home/admin
admin
hostname
```

## SSH 失败时的快速判断

### 1. 主机指纹失败

现象：

```text
Host key verification failed
```

处理：

```powershell
$kh = Join-Path $env:TEMP 'codex_server_known_hosts'
ssh -o UserKnownHostsFile=$kh -o StrictHostKeyChecking=accept-new user@host "echo OK"
```

不要直接清理用户正式 `known_hosts`，除非确认旧指纹确实无用。

### 2. 公钥没有被服务器识别

`ssh -vvv` 中只看到：

```text
Offering public key
Authentications that can continue
Permission denied
```

但没有：

```text
Server accepts key
```

处理：

- 检查公钥是否加到正确用户的 `authorized_keys`。
- 检查 `.ssh` 和 `authorized_keys` 权限。
- 检查用户名是否正确。

### 3. 服务器接受 key，但仍失败

现象：

```text
Server accepts key
sign_and_send_pubkey
we did not send a packet
Permission denied
```

优先检查本地私钥是否带口令。非交互 Codex 不能输入私钥口令。

处理：

- 换无口令专用 key。
- 或配置 ssh-agent，但自动化中更推荐无口令专用 key 加最小权限。

### 4. 怀疑服务器策略

服务器上查：

```bash
sudo grep -E '^(AuthenticationMethods|PubkeyAuthentication|PasswordAuthentication|KbdInteractiveAuthentication|UsePAM|AllowUsers|DenyUsers|Match)' /etc/ssh/sshd_config
sudo tail -n 80 /var/log/secure | grep sshd
```

如果云防火墙可能限制来源，查安全组入方向 TCP 22，或服务器上查：

```bash
sudo iptables -S
sudo firewall-cmd --list-all 2>/dev/null
sudo fail2ban-client status 2>/dev/null
sudo ss -lntp | grep ':22'
```

## 远程定位项目和进程

连接成功后先只读检查：

```powershell
$kh = Join-Path $env:TEMP 'codex_server_known_hosts'
ssh -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  admin@118.190.201.47 "find /home/admin /root -maxdepth 5 -name web_app.py 2>/dev/null"
```

查进程：

```powershell
ssh ... admin@118.190.201.47 "ps -ef | grep -E 'uvicorn|web_app|python' | grep -v grep || true"
```

查端口：

```powershell
ssh ... admin@118.190.201.47 "ss -lntp | grep ':80 ' || true"
```

## 同步文件前先备份

远程没有 `git` 时，不能依赖 `git status`。先做文件级备份。

```powershell
$remote = 'cd /home/admin/mode3_10minstudy && ts=$(date +%Y%m%d_%H%M%S) && backup=/home/admin/mode3_10minstudy_backup_$ts && mkdir -p $backup/static $backup/tests && cp web_app.py prompt_builder.py $backup/ && cp static/app.js $backup/static/ && cp tests/test_web_app_helpers.py $backup/tests/ && echo $backup'
ssh -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  admin@118.190.201.47 $remote
```

注意：PowerShell 中远程 `$(date ...)` 必须放在单引号字符串里，避免被本地解析。

## 上传文件

```powershell
scp -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  web_app.py prompt_builder.py `
  admin@118.190.201.47:/home/admin/mode3_10minstudy/

scp -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  static\app.js `
  admin@118.190.201.47:/home/admin/mode3_10minstudy/static/app.js
```

## 远程测试

```powershell
ssh -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  admin@118.190.201.47 "cd /home/admin/mode3_10minstudy && .venv/bin/python -m unittest tests.test_web_app_helpers"
```

## 重启服务

推荐把脚本通过 stdin 管给远程 `bash -s`，避免复杂转义。

```powershell
$remote = @'
cd /home/admin/mode3_10minstudy || exit 1
pids=$(pgrep -f 'uvicorn web_app:app' || true)
if [ -n "$pids" ]; then
  kill $pids
  sleep 2
fi
nohup /home/admin/mode3_10minstudy/.venv/bin/python -m uvicorn web_app:app --host 0.0.0.0 --port 80 > /home/admin/mode3_10minstudy/uvicorn.log 2>&1 &
echo $!
'@

$remote | ssh -i $env:USERPROFILE\.ssh\codex_server_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  admin@118.190.201.47 bash -s
```

注意：`pgrep -f` 的 pattern 不要以 `-` 开头，否则会被当成 `pgrep` 参数。

## 验证部署

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://118.190.201.47/" -TimeoutSec 15
Invoke-WebRequest -UseBasicParsing -Uri "http://118.190.201.47/static/app.js" -TimeoutSec 15
Invoke-WebRequest -UseBasicParsing -Uri "http://118.190.201.47/api/users" -TimeoutSec 15
```

远程确认端口归属：

```powershell
ssh ... admin@118.190.201.47 "ps -ef | grep 'uvicorn web_app:app' | grep -v grep; ss -lntp | grep ':80 ' || true; tail -n 40 /home/admin/mode3_10minstudy/uvicorn.log"
```

## 本项目当前可用配置

当前已验证可用的 key：

```text
C:\Users\32563\.ssh\codex_118_plain_ed25519
```

当前可用命令：

```powershell
$kh = Join-Path $env:TEMP 'codex_118_ssh_known_hosts'
ssh -i $env:USERPROFILE\.ssh\codex_118_plain_ed25519 `
  -o IdentityAgent=none `
  -o IdentitiesOnly=yes `
  -o UserKnownHostsFile=$kh `
  -o StrictHostKeyChecking=accept-new `
  admin@118.190.201.47 "echo OK && pwd && whoami && hostname"
```

远程项目：

```text
/home/admin/mode3_10minstudy
```

远程服务：

```text
/home/admin/mode3_10minstudy/.venv/bin/python -m uvicorn web_app:app --host 0.0.0.0 --port 80
```

