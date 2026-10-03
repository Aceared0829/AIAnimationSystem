// Fill out your copyright notice in the Description page of Project Settings.


#include "AnimNotify_FoleyEvent.h"
#include "BlueprintGameplayTagLibrary.h"

#include "Animation/AnimNotifyLibrary.h"

#include "Components/SkeletalMeshComponent.h"

#include "Engine/World.h"

#include "Kismet/GameplayStatics.h"

#include "CommonGameplay/Foley/DataAsset_FoleyAudioBank.h"

#include "UObject/ConstructorHelpers.h"

UAnimNotify_FoleyEvent::UAnimNotify_FoleyEvent()
{
	VisLogDebugColor = FLinearColor(1.0f,0.054146f,0.89767f,1.0f);
	Event = FGameplayTag::EmptyTag;
	Side = EFoleyEventSide::None;
	VolumeMultiplier = 1.0f;
	PitchMultiplier = 1.0f;
	
	if (const ConstructorHelpers::FObjectFinder<UDataAsset_FoleyAudioBank> FoleyEventBankOfPath(
		TEXT("/Script/UMWSamplePreview.DataAsset_FoleyAudioBank'/Game/Audio/Foley/DS_DefaultFoleyEventAudioBank.DS_DefaultFoleyEventAudioBank'"));
		FoleyEventBankOfPath.Succeeded())
	{
		DefaultBank = FoleyEventBankOfPath.Object.Get();
	}
	
#if WITH_EDITORONLY_DATA
	NotifyColor = FColor(255,200,200,255);
	bShouldFireInEditor = true;
#endif
}

void UAnimNotify_FoleyEvent::Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation,
                                    const FAnimNotifyEventReference& EventReference)
{
	Super::Notify(MeshComp, Animation, EventReference);

	if (UAnimNotifyLibrary::IsBlendingOut(EventReference))
	{
		return;
	}

	if (!MeshComp || !Animation)
	{
		return;
	}

	AActor* Owner = MeshComp->GetOwner();
	if (!Owner)
	{
		return;
	}

	if (UFoleyEventsComponent* FoleyEventsComp = Owner->GetComponentByClass<UFoleyEventsComponent>())
	{
		FoleyEventsComp->PlayFoleyEvent(Event, FFoleyEventParams(Side, VolumeMultiplier, PitchMultiplier));
		return;
	}

	// 没有 FoleyEventsComponent 时走 2D 播放：不要再用 FoleyEventsComp（此时为 nullptr）
	if (!DefaultBank)
	{
		return;
	}

	bool bSuccess = false;
	USoundBase* Sound = DefaultBank->GetFoleyAudioAssetByTag(Event, bSuccess);
	if (!bSuccess || !Sound)
	{
		return;
	}

	UWorld* World = MeshComp->GetWorld();
	if (!World)
	{
		return;
	}

	UGameplayStatics::PlaySound2D(
		World,
		Sound,
		VolumeMultiplier,
		PitchMultiplier,
		0.0f,
		nullptr,
		nullptr,
		true
	);
}

FString UAnimNotify_FoleyEvent::GetNotifyName_Implementation() const
{
	// 目的：在动画通知列表里显示一个更短的名字（取 GameplayTag 最后一级）。
	// 例："Foley.Event.Footstep" -> "Footstep"

	// 兜底：没有设置 Tag 时给一个固定显示名，避免空字符串。
	if (!Event.IsValid())
	{
		return TEXT("FoleyEvent:{None}");
	}

	const FString DebugTagString = UBlueprintGameplayTagLibrary::GetDebugStringFromGameplayTag(Event);

	FString Left;
	FString Right;
	const bool bSplitOk = DebugTagString.Split(TEXT("."), &Left, &Right, ESearchCase::IgnoreCase, ESearchDir::FromEnd);

	// 如果 Split 失败（例如没有 '.'），那就直接使用完整 Tag 字符串。
	const FString& ShortName = bSplitOk ? Right : DebugTagString;
	return FString::Printf(TEXT("FoleyEvent:{%s}"), *ShortName);
}
