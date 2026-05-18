# TXT 长篇小说转 EPUB 工具

这是一个面向中文长篇 TXT 小说的 EPUB 转换工具。它可以把普通 `.txt` 文件整理成带目录、元数据、封面和阅读器兼容结构的 `.epub` 文件，适合用来处理网络小说、长篇文稿、旧编码 TXT 和批量书库整理。

项目提供两种使用方式：

- **Windows 可视化应用**：直接双击 `TxtToEpubConverter.exe`，在界面里选择文件、调整参数并转换。
- **Python 命令行工具**：使用 `txt_to_epub.py` 批量转换，适合脚本化和自动化处理。

转换核心使用 Python 标准库实现，不依赖 Calibre、ebooklib 或 chardet。桌面界面采用 `pywebview + React + Vite + TailwindCSS`，前端负责现代化交互，后端继续复用稳定的 Python 转换逻辑。

## 功能亮点

- 自动识别常见中文 TXT 编码，包括 `utf-8`、`gb18030`、`big5`、`utf-16`
- 支持单文件转换，也支持文件夹批量递归转换
- 自动识别章节标题并生成 EPUB 目录
- 支持额外章节正则，适配特殊小说格式
- 支持封面图片、作者、书名、语言、出版者、简介等元数据
- 支持嵌入 CJK 字体，改善生僻字在阅读器中的显示
- 支持预览章节目录，不生成 EPUB
- 转换后生成 `conversion_report.txt` 和 `conversion_report.json`
- 提供现代 Web 风格 Windows GUI 和可复现的打包脚本

## 快速开始

如果你只想直接使用 Windows 桌面版，下载或打开仓库根目录里的：

```text
TxtToEpubConverter.exe
```

打开后可以在界面中完成这些操作：

- 添加 TXT 文件或包含 TXT 的文件夹
- 设置输出目录、编码、书名、作者、封面和字体
- 开启递归转换、覆盖同名文件、保留 TXT 自带目录、弱标题识别
- 填写额外章节正则和 EPUB 元数据
- 先预览目录，再正式转换
- 查看运行日志和打开输出目录

默认输出目录会新建在：

```text
E:\txt-epub\txt转epub_时间戳
```

如果你的电脑没有这个目录，程序会自动创建；也可以在 GUI 或命令行中手动指定输出目录。

## 命令行用法

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
python txt_to_epub.py "D:\小说" --recursive --output-dir "E:\txt-epub\我的epub"
```

强制指定编码：

```powershell
python txt_to_epub.py "D:\小说\古早小说.txt" --encoding gb18030
```

添加封面和作者：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --author "作者名" --cover-image "D:\封面\cover.jpg"
```

## 章节识别

默认支持常见中文小说章节格式，例如：

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

如果 TXT 使用特殊格式，可以额外传入章节正则：

```powershell
python txt_to_epub.py "D:\小说\特殊格式.txt" --chapter-regex "^【第.+?章】.*$"
```

如果章节格式是 `一、标题` 或 `1. 标题`，可以打开弱标题识别：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --allow-weak-numbered-title
```

这个选项有正文误判风险，所以默认关闭。

## 生僻字与字体

脚本默认会自动尝试多种编码，并尽量避免用“忽略错误”的方式吞掉无法识别的字。如果发现编码不干净，相关警告会写入转换报告。

如果阅读器显示生僻字为方框，可以嵌入 CJK 字体：

```powershell
python txt_to_epub.py "D:\小说\某本小说.txt" --font "D:\字体\NotoSerifCJKsc-Regular.otf"
```

推荐字体：

- Noto Serif CJK SC
- Noto Sans CJK SC
- Source Han Serif SC
- Source Han Sans SC

注意：嵌入完整中文字体会显著增大 EPUB 文件体积。

## 从源码运行 GUI

GUI 由 Python 后端和 React 前端组成。首次运行需要安装依赖并构建前端：

```powershell
python -m pip install -r requirements-gui.txt
cd frontend
npm install
npm run build
cd ..
python txt_to_epub_gui.py
```

## 打包 Windows EXE

项目提供 `build_exe.ps1`，会自动创建 `.venv-build` 专用环境，安装 GUI/打包依赖，构建前端，并使用 PyInstaller 生成 Windows 可执行文件。

首次打包：

```powershell
.\build_exe.ps1 -InstallDeps
```

之后重新打包：

```powershell
.\build_exe.ps1
```

默认生成单文件：

```text
dist\TxtToEpubConverter.exe
```

脚本还会同步复制一份到项目根目录：

```text
TxtToEpubConverter.exe
```

如果更希望生成传统文件夹形式：

```powershell
.\build_exe.ps1 -OneDir
```

文件夹模式入口：

```text
dist\TxtToEpubConverter\TxtToEpubConverter.exe
```

## 项目结构

```text
.
├─ txt_to_epub.py          # TXT 到 EPUB 的核心转换逻辑
├─ txt_to_epub_gui.py      # pywebview 桌面壳和 Python API
├─ frontend/               # React + Vite + Tailwind 前端
├─ samples/                # 示例 TXT
├─ build_exe.ps1           # Windows 打包脚本
├─ requirements-gui.txt    # Python GUI/打包依赖
└─ TxtToEpubConverter.exe  # 已构建的 Windows 单文件应用
```

## 输出报告

每次正式转换后，输出文件夹里会生成：

```text
conversion_report.txt
conversion_report.json
```

报告会记录：

- 每本书的源文件和输出路径
- 检测到的编码
- 章节数量
- 是否跳过 TXT 自带目录
- 编码或 EPUB 校验警告
- 失败原因

## 适合的使用场景

这个工具适合需要经常整理中文 TXT 小说的人：例如把旧网站下载的长篇 TXT 转成 EPUB、给阅读器制作带目录的书籍、批量处理多个小说文件夹，或者在保留 Python 可维护性的同时获得一个比较现代的桌面应用界面。
