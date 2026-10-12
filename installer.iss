; 西西的声骸评分工具 安装包脚本
; 版本号由 CI 传入：ISCC /DMyAppVersion=v0.1.0

[Setup]
AppName=西西的声骸评分工具
AppVersion={#MyAppVersion}
AppPublisher=xixi
DefaultDirName={autopf}\xixi-echo
; lowest 免管理员；Inno 在 lowest 下默认隐藏目录页，显式打开让用户自选安装位置
PrivilegesRequired=lowest
DisableDirPage=no
OutputDir=output
OutputBaseFilename=xixi-echo-setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=西西的声骸评分工具
SetupIconFile=assets\xixi-echo.ico

[Languages]
; 官方安装程序自 6.5 起不再自带简中语言文件，随仓库分发（installer/ChineseSimplified.isl）
Name: "chinesesimplified"; MessagesFile: "installer\ChineseSimplified.isl"

[Files]
Source: "dist\xixi-echo\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\西西的声骸评分工具"; Filename: "{app}\xixi-echo.exe"
Name: "{userstartup}\xixi-echo"; Filename: "{app}\xixi-echo.exe"

[Run]
; shellexec：exe 清单要求管理员，普通权限安装器必须走 ShellExec 才能弹 UAC（CreateProcess 报 740）
; 不带 skipifsilent：静默更新装完也自动拉起新版；runasoriginaluser 以安装者身份启动
Filename: "{app}\xixi-echo.exe"; Flags: nowait shellexec runasoriginaluser
