# 具体问题姿态补参考实验（2026-09-23）

使用现有 V2 权重完成已知源动画重建实验。首次重建后，按骨盆相对坐标计算左右手臂、左右腿、躯干头部五组误差，选最差姿态补完整姿态条件，再解码；第二次补帧重新计算误差。参考间隔至少 3 帧。没有直接覆盖输出姿态，没有训练新权重，也没有替换 UE 模型。

## 实验边界

- 长动作保持窗口 24、步长 4、播放延迟 8，只使用历史数据；共同计分区间从源帧 28 到末帧前 8 帧，不覆盖起手暖机与结束排空。
- 短片使用原始 11～21 帧，保持末帧补到 24；仅原始帧计分。它是完整已知短片离线诊断，不代表实时暖机效果。
- 测试集 24 条：短姿态 7、其他复杂动作 13、跑酷 4。另单独复核验证集 9 条跑酷。共 33 条，不混入训练集。测试集一条 45 帧扑倒动画无法满足上述两种计分区间，跳过。
- `targeted3` 为首尾加一个问题姿态，`targeted4` 为首尾加两个；`shape4` 按源姿态差异选两个中间帧。`dense_diagnostic` 全有效帧给条件，仅用于诊断。
- 每个动作先统计平均关节 RMSE，再对动作等权平均，单位 cm。当前脚本每个候选都会重新编码解码，未作缓存复用，没有性能收益证据。

## 实测结果

|范围|首尾 2|形状 4|问题姿态 3|问题姿态 4|
|---|---:|---:|---:|---:|
|短姿态 7|9.662|8.508|8.684|8.437|
|其他复杂动作 13|8.780|8.252|8.482|8.205|
|跑酷测试集 4|7.409|7.202|7.201|7.012|
|跑酷验证集 9|6.292|6.235|6.081|6.103|

问题姿态 3 的关节平均误差在 13 条跑酷上全部下降，但部分改善极小；问题姿态 4 在测试集只改善 2/4，验证集改善 8/9。不能统一规定每个动作都补两个。

|跑酷测试动作|首尾 2|问题姿态 3|问题姿态 4|
|---|---:|---:|---:|
|Catch Hurdle low run|11.457|11.212|11.036|
|Catch Hurdle med stand|4.420|4.363|4.447|
|Mantle run Rfoot|4.589|4.582|4.602|
|Vault run Lfoot|9.170|8.646|7.964|

Vault 的手臂、腿部和躯干组平均误差都下降；其基线最差帧 33 的全身误差从 28.67 降至 21.22 cm，仍然很大。低障碍右腿组 18.55→17.13 cm，仍是主要问题。没有接触标签及场景几何，本实验不能判断手是否贴住障碍、脚是否正确落地。

跑酷测试集加速度误差 3.410→3.463→3.475 cm/帧²（首尾2→问题3→问题4），验证集为 2.930→2.913→3.001。因此姿态更接近不等于抽搐已解决。全帧条件反而使跑酷关节平均误差增大：测试集 8.250、验证集 7.351；当前条件是软约束。

## 短姿态需要区分含义

4 个 AimOffset 和 Sprint Lean 的原始骨架位置完全静止，中间补帧没有增加不同姿态信息，改变的是条件位置与密度。Run Lean 有小幅连续变化；injured 姿态组相邻帧平均骨架变化 17.15 cm，需要进一步检查源资产是否为离散姿态集合，不能直接把帧差称作动画抖动。

injured 的短片误差 36.09→29.37 cm，但左腿组 30.17→35.97 cm；全身平均下降仍可能掩盖肢体恶化。

额外逐姿态实验：将每个源姿态独立保持 24 帧，只取解码中心帧 12，比较首尾条件和首尾加中心条件。5 个静态姿态均改善，例如极限 AimOffset 8.05→6.84 cm；injured 33.93→30.13 cm，残差仍大。Run Lean 5.89→5.35 cm，且不如保留原有时间上下文的短片基线 4.47 cm。逐姿态独立解码不适合直接替代连续动作推理。

## 当前判断

跑酷先试一个针对问题的中间参考更稳；Vault 等个别动作有理由再补第二个，须同时验收肢体误差和连续性。短静态姿态可单独研究中心姿态条件；连续短动作保留上下文；离散姿态集合先确认资产语义。参考补充无法单独解释或消除剩余大偏差。当前只有源姿态可获得时才能按重建误差选帧，不能直接用于未知目标动作生成。

## 复现与产物

使用仓库 `.venv/Scripts/python.exe`：

```powershell
python -m inference.profiling.evaluate_targeted_references --checkpoint training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt --output output/ai_animation_runtime_pose_references/targeted.json
python -m inference.profiling.evaluate_targeted_references --checkpoint training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt --selection validation-traversal --output output/ai_animation_runtime_pose_references/targeted_traversal_validation.json
python -m inference.profiling.evaluate_isolated_poses
python -m inference.profiling.render_targeted_references output/ai_animation_runtime_pose_references/targeted.json
python -m unittest inference.profiling.test_pose_references inference.profiling.test_streaming_comparison
```

JSON 保存逐片、逐肢体误差和新增参考源帧；同名 NPZ 保存实际计分骨架。`targeted_traversal_comparison.mp4` 为离线骨架对照：左首尾条件、右补两个问题姿态；蓝色源骨架、橙色重建。每个片段按 30 FPS 播放，较短片段保持末帧，重复三遍。静态图展示基线各片最差帧，两侧相同源帧，不能替代完整视频。不是 UE 蒙皮或实际障碍交互验证。
