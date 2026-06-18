; ============================================================
;  量化终端 · quantify   Inno Setup 安装脚本
;  编译后生成「量化终端_安装程序_v1.0.exe」——双击即可安装、
;  自动建桌面快捷方式 + 开始菜单,并可在"添加/删除程序"里卸载。
; ============================================================

#define MyAppName "量化终端"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "张佳泽"
#define MyAppExeName "量化终端.exe"
#define MyAppCopyright "Copyright © 2026 张佳泽 (软件工程师). 保留所有权利。"
#define SrcDir "D:\桌面\quantify\dist\量化终端"

[Setup]
; AppId 唯一标识本程序(升级/卸载靠它识别),不要随便改
AppId={{B7E8F3A2-1C4D-4E5F-9A6B-2D3C4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppContact=张佳泽(软件工程师)
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=量化终端 安装程序
; 默认装到当前用户(免 UAC 管理员弹窗);用户可在向导里改安装位置
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
; 生成的安装包放到桌面
OutputDir=D:\桌面
OutputBaseFilename=量化终端_安装程序_v1.0
SetupIconFile=D:\桌面\quantify\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "cn"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Messages]
; 安装向导窗口左下角的署名
cn.BeveledLabel=© 2026 张佳泽 · 软件工程师

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式:"

[Files]
; 把打包好的整个文件夹(exe + _internal)装进去
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; 使用说明(主副本在项目根目录,确保每次都带上,不受打包清空影响)
Source: "D:\桌面\quantify\使用说明.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时连运行产生的缓存一起清掉
Type: filesandordirs; Name: "{app}\data"
