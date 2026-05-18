# TXT 长篇小说转 EPUB 工具

这个目录里的 `txt_to_epub.py` 是一个纯 Python 标准库转换器，用来把中文 TXT 网络小说转换成带目录的 EPUB。

默认输出目录会新建在：

```text
E:\不知道\txt转epub_时间戳
```

如果你的电脑上没有这个文件夹，脚本会自动创建；如果 E 盘不存在或权限不足，可以用 `--output-dir` 改到其他位置。

## 最常用命令

转换单个 TXT：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt"
```

转换一个文件夹里的所有 TXT：

```powershell
python txt_to_epub.py "D:\小说" --recursive
```

先预览目录，不生成 EPUB：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --preview
```

指定输出目录：

```powershell
python txt_to_epub.py "D:\小说" --recursive --output-dir "E:\不知道\我的epub"
```

## 可视化 GUI / Windows EXE

已经提供可直接双击运行的 Windows 版本：

```text
TxtToEpubConverter.exe
```

桌面界面采用 `pywebview + React + Vite + TailwindCSS`，转换逻辑仍然复用 Python 后端 `txt_to_epub.py`。

如果想在应用内选择文件和控制参数，可以直接运行：

```powershell
python -m pip install -r requirements-gui.txt
cd frontend
npm install
npm run build
cd ..
python txt_to_epub_gui.py
```

GUI 支持：

- 添加单个 TXT 或整个文件夹
- 现代 Web 风格桌面界面
- 设置输出目录、编码、作者、书名、封面、字体
- 开关递归转换、覆盖同名 EPUB、保留 TXT 自带目录、弱标题识别
- 填写额外章节正则、语言、出版者、简介
- 先预览目录，再正式转换
- 查看运行日志和打开输出目录

## 打包成 Windows EXE

项目提供了 `build_exe.ps1`。如果已经安装 GUI 和打包依赖：

```powershell
.\build_exe.ps1
```

如果还没有安装依赖，可以让脚本先安装再打包：

```powershell
.\build_exe.ps1 -InstallDeps
```

脚本默认会在项目目录创建 `.venv-build` 作为专用打包环境，避免和你现有 Python/Anaconda 包冲突。依赖列表在 `requirements-gui.txt`，目前使用开源的 `pywebview` 和 `pyinstaller`；前端依赖在 `frontend/package.json`。如果你确实想使用当前 Python 环境，可以加 `-UseCurrentPython`。

默认会生成单文件 EXE：

```text
dist\TxtToEpubConverter.exe
```

单文件模式还会同步复制一份到项目根目录：

```text
TxtToEpubConverter.exe
```

如果更希望生成传统文件夹形式，运行：

```powershell
.\build_exe.ps1 -OneDir
```

文件夹模式的入口在：

```text
dist\TxtToEpubConverter\TxtToEpubConverter.exe
```

## 生僻字与编码

脚本默认会自动尝试：

- `utf-8`
- `gb18030`
- `big5`
- `utf-16`

其中 `gb18030` 对简体中文和很多生僻字更友好。脚本不会用“忽略错误”的方式吞掉无法识别的字；如果发现编码不干净，会写进 `conversion_report.txt`。

如果你确定 TXT 是某种编码，可以强制指定：

```powershell
python txt_to_epub.py "D:\小说\古早小说.txt" --encoding gb18030
```

## 章节目录识别

默认支持常见标题：

- `第1章 标题`
- `第一章 标题`
- `第001章 标题`
- `第十卷 标题`
- `卷一 标题`
- `序章`
- `楔子`
- `终章`
- `番外`
- `大结局`

如果你的 TXT 用的是特殊格式，可以额外传入章节正则：

```powershell
python txt_to_epub.py "D:\小说\特殊格式.txt" --chapter-regex "^【第.+?章】.*$"
```

如果章节格式是 `一、标题` 或 `1. 标题`，可以打开弱标题识别：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --allow-weak-numbered-title
```

这个选项有正文误判风险，所以默认关闭。

## 嵌入字体

如果阅读器显示生僻字为方框，可以嵌入 CJK 字体：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --font "D:\字体\NotoSerifCJKsc-Regular.otf"
```

建议字体：

- Noto Serif CJK SC
- Noto Sans CJK SC
- Source Han Serif SC
- Source Han Sans SC

注意：嵌入完整中文字体会显著增大 EPUB 文件体积。

## 封面和元数据

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --author "作者名" --cover-image "D:\封面\cover.jpg"
```

批量转换时不建议使用 `--title`，因为它会让多本书使用同一个书名。

## 输出报告

每次正式转换后，输出文件夹里会生成：

```text
conversion_report.txt
conversion_report.json
```

里面会记录：

- 每本书的输出路径
- 检测到的编码
- 章节数量
- 是否跳过了 TXT 自带目录
- 编码或 EPUB 校验警告
- 失败原因
