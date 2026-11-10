# 文献转 Abaqus 白模

导入试件描述，检查带出处的参数，再批量生成可编辑的 Abaqus 梁柱装配。

## 运行

1. 安装 Go 1.22+ 和 Python 3.10+。在本目录运行 python -m pip install -r requirements.txt，再运行 go run .
2. 打开 http://127.0.0.1:8787，上传 examples/specimen.pdf 或 examples/specimen.docx。
3. 在文字框填“梁高改成 550 mm 和 600 mm”，点提取。核对参数及出处后下载生成包。
4. 解压生成包，在解压目录运行 abaqus cae noGUI=build_cae.py，得到 white-models.cae，含原版和变体。

## 输入和模型

- 支持 PDF 文本层、DOCX 正文与表格、UTF-8 TXT。PDF 最多 60 页，建议先截取目标试件页。
- PNG/JPEG 读取依赖 PATH 上的 Tesseract，默认需要 eng 与 chi_sim 语言包，可通过 WHITE_OCR_LANG 设置语言。设置 WHITE_OCR=1 可对没有文本层的 PDF 页尝试 OCR。
- 当前提取明确标签和单位，例如“X向半跨 3 m”“梁截面 300×500 mm”。参数缺项或冲突可手工确认。图片 OCR 识别标注文字，图形拓扑由十字形／T 形模板确定。
- 两向梁使用同一矩形截面，中心柱与各梁是独立实体实例。半跨以柱轴线计，柱高指梁底标高以下的高度。输出是几何装配，后续连接、材料、网格、边界及求解在 CAE 中另设。
- 网页监听本机地址。输出是参数 JSON、SVG 预览和 CAE 建模脚本。安装了 Abaqus 的机器可以生成原生 CAE。
