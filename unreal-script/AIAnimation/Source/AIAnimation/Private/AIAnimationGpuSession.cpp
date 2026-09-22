// Copyright ZhaoZining. All Rights Reserved.

// 模型装载发生在初始化期，计时覆盖 RunSync 的上传、GPU 执行和下载等待。
#include "AIAnimationGpuSession.h"
#include "NNE.h"
#include "NNEModelData.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"

TSharedPtr<FAIAnimationGpuSession> FAIAnimationGpuSession::Create(const UAIAnimationModel& Asset, FString& OutError, bool bCreateInference)
{
	check(IsInGameThread());
	if (!Asset.ModelData || Asset.RootBone.IsNone() || Asset.WindowFrames < 8 || Asset.WindowFrames > 64 || Asset.WindowFrames % 4 || Asset.Bones.IsEmpty() || Asset.Bones.Num() > 512
		|| !FMath::IsFinite(Asset.SampleRate) || Asset.SampleRate <= 0.0f || Asset.TrainingSignature.Len() != 64)
	{
		OutError = TEXT("模型资产缺失或窗口、骨架、采样率不合法。");
		return nullptr;
	}
	TSet<FName> Names;
	for (int32 Index = 0; Index < Asset.Bones.Num(); ++Index)
	{
		const FAIAnimationBone& Bone = Asset.Bones[Index];
		if (Bone.Name.IsNone() || Bone.Name == Asset.RootBone || Names.Contains(Bone.Name) || Bone.ReferenceTransform.ContainsNaN()
			|| (Index == 0 ? Bone.ParentIndex != INDEX_NONE : Bone.ParentIndex < 0 || Bone.ParentIndex >= Index))
		{
			OutError = TEXT("模型骨骼名称、拓扑或参考变换不合法。");
			return nullptr;
		}
		Names.Add(Bone.Name);
	}
	TSharedPtr<FAIAnimationGpuSession> Session = MakeShared<FAIAnimationGpuSession>();
	Session->Bones = Asset.Bones;
	Session->RootBone = Asset.RootBone;
	Session->WindowFrames = Asset.WindowFrames;
	Session->SampleRate = Asset.SampleRate;
	if (!bCreateInference)
	{
		return Session;
	}
	TWeakInterfacePtr<INNERuntimeGPU> Runtime = UE::NNE::GetRuntime<INNERuntimeGPU>(TEXT("NNERuntimeORTDml"));
	if (!Runtime.IsValid() || Runtime->CanCreateModelGPU(Asset.ModelData) != UE::NNE::EResultStatus::Ok)
	{
		OutError = TEXT("DirectML GPU 后端不可用或不支持该模型。");
		return nullptr;
	}
	TSharedPtr<UE::NNE::IModelGPU> Model = Runtime->CreateModelGPU(Asset.ModelData);
	TSharedPtr<UE::NNE::IModelInstanceGPU> Instance = Model ? Model->CreateModelInstanceGPU() : nullptr;
	if (!Instance || Instance->GetInputTensorDescs().Num() != 1 || Instance->GetOutputTensorDescs().Num() != 1)
	{
		OutError = TEXT("GPU 实例创建失败，或模型输入输出数量不匹配。");
		return nullptr;
	}
	const TArray<uint32> InputDimensions = { 1u, uint32(Asset.WindowFrames + 1), uint32(Asset.Bones.Num()), 12u };
	const TArray<UE::NNE::FTensorShape> Shapes = { UE::NNE::FTensorShape::Make(InputDimensions) };
	if (Instance->SetInputTensorShapes(Shapes) != UE::NNE::EResultStatus::Ok || Instance->GetOutputTensorShapes().Num() != 1)
	{
		OutError = TEXT("GPU 模型无法解析固定输入输出形状。");
		return nullptr;
	}
	const uint64 NumOutputValues = uint64(Asset.WindowFrames) * Asset.Bones.Num() * 12;
	if (Instance->GetOutputTensorShapes()[0].Volume() != NumOutputValues || Instance->GetInputTensorDescs()[0].GetDataType() != ENNETensorDataType::Float
		|| Instance->GetOutputTensorDescs()[0].GetDataType() != ENNETensorDataType::Float)
	{
		OutError = TEXT("GPU 模型输出形状或精度与契约不匹配。");
		return nullptr;
	}
	Session->Output.SetNumZeroed(int32(NumOutputValues));
	Session->Instance = MoveTemp(Instance);
	return Session;
}

bool FAIAnimationGpuSession::Run(TConstArrayView<float> Input, double& OutMilliseconds)
{
	TRACE_CPUPROFILER_EVENT_SCOPE(AIAnimation_GPU_RunSync);
	if (!Instance || IsInGameThread() || Input.Num() != (WindowFrames + 1) * Bones.Num() * 12)
	{
		return false;
	}
	UE::NNE::FTensorBindingCPU InputBinding { const_cast<float*>(Input.GetData()), uint64(Input.Num()) * sizeof(float) };
	UE::NNE::FTensorBindingCPU OutputBinding { Output.GetData(), uint64(Output.Num()) * sizeof(float) };
	const double Start = FPlatformTime::Seconds();
	const UE::NNE::EResultStatus Status = Instance->RunSync(MakeArrayView(&InputBinding, 1), MakeArrayView(&OutputBinding, 1));
	OutMilliseconds = (FPlatformTime::Seconds() - Start) * 1000.0;
	if (Status != UE::NNE::EResultStatus::Ok)
	{
		return false;
	}
	for (const float Value : Output)
	{
		if (!FMath::IsFinite(Value))
		{
			return false;
		}
	}
	return true;
}
