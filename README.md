# HyperKitchen Prototype

这是一个厨房助手快速原型，旨在展示通过手势控制进行烹饪辅助的端到端流程。

## 功能特性

1. **视频上传与分析**：支持上传烹饪视频，自动分析生成烹饪步骤（目前使用Mock数据演示）。
2. **步骤展示**：清晰展示每个步骤的标题、描述和关键信息高亮。
3. **视频切片播放**：点击步骤自动跳转到对应视频片段。
4. **手势控制**（需解决模型下载问题）：
   - 左手向右挥动 -> 下一步
   - 左手向左挥动 -> 上一步
   - 右手OK/举手 -> 暂停/继续
   - 双手举起 -> 返回概览

## 快速开始

### 前置要求

- Node.js 18+
- Python 3.11+
- FFmpeg (需添加到系统环境变量)

### 安装与运行

#### 1. 后端服务

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
# source venv/bin/activate

pip install -r requirements.txt
python app.py
```

后端服务将运行在 `http://localhost:5000`。

#### 2. 前端服务

```bash
cd frontend
npm install
npm run dev
```

前端服务将运行在 `http://localhost:5173`。

## 注意事项与已知问题

1. **AI模型依赖**：由于网络环境限制，`volcengine-python-sdk-ark-runtime` 安装失败，目前后端使用Mock数据模拟AI分析结果。如需接入真实AI，请确保网络通畅并取消 `backend/app.py` 中的相关注释，配置 `ARK_API_KEY`。
2. **手势识别**：`mediapipe` 初始化时需要下载模型文件，如遇网络问题导致 `FileNotFoundError`，手势控制功能将不可用。建议在网络通畅环境下运行或手动下载模型文件。
3. **FFmpeg**：视频切片功能依赖 FFmpeg，请确保服务器已安装 FFmpeg 并配置好环境变量。

## 测试指南

1. 启动前后端服务。
2. 打开浏览器访问 `http://localhost:5173`。
3. 点击上传区域，选择一个烹饪视频文件（MP4格式）。
4. 等待“分析”完成（模拟过程）。
5. 查看生成的步骤列表。
6. 点击步骤，右侧视频播放器将跳转到对应时间点。
7. （如果手势识别可用）尝试对着摄像头做手势控制播放。

## 目录结构

- `backend/`: Flask 后端，处理视频上传、切片和手势识别。
- `frontend/`: React 前端，提供用户交互界面。
- `uploads/`: 上传的原始视频保存目录。
- `slices/`: 切片后的视频保存目录。

## 替换视频与数据

若要替换演示用的 Mock 数据，请修改 `backend/app.py` 中的 `process_video` 函数中的 `steps` 数组。
