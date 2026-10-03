// Fill out your copyright notice in the Description page of Project Settings.


#include "DataAsset_FoleyAudioBank.h"

#include "UObject/ConstructorHelpers.h"

UDataAsset_FoleyAudioBank::UDataAsset_FoleyAudioBank()
{
	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_WalkOfPath(
		TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Walk.MSS_FoleySound_Walk'"));
		MSS_FoleySound_WalkOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Walk")),
			MSS_FoleySound_WalkOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_RunSoftOfPath(
		TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Run_Soft.MSS_FoleySound_Run_Soft'"));
		MSS_FoleySound_RunSoftOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Run")),
			MSS_FoleySound_RunSoftOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_JumpOfPath(
		TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Jump.MSS_FoleySound_Jump'"));
		MSS_FoleySound_JumpOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Jump")),
			MSS_FoleySound_JumpOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_LandOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Land.MSS_FoleySound_Land'"));
	MSS_FoleySound_LandOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Land")),
			MSS_FoleySound_LandOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_ScuffOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Scuff.MSS_FoleySound_Scuff'"));
	MSS_FoleySound_ScuffOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Scuff")),
			MSS_FoleySound_ScuffOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_HandplantOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Handplant.MSS_FoleySound_Handplant'"));
	MSS_FoleySound_HandplantOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Handplant")),
			MSS_FoleySound_HandplantOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_RunBackwdsOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_RunBackwards.MSS_FoleySound_RunBackwards'"));
	MSS_FoleySound_RunBackwdsOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.RunBackwds")),
			MSS_FoleySound_RunBackwdsOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_ScuffPivotOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_ScuffPivot.MSS_FoleySound_ScuffPivot'"));
	MSS_FoleySound_ScuffPivotOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.ScuffPivot")),
			MSS_FoleySound_ScuffPivotOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_ScuffWallOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_ScuffWall.MSS_FoleySound_ScuffWall'"));
	MSS_FoleySound_ScuffWallOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.ScuffWall")),
			MSS_FoleySound_ScuffWallOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_RunStrafeOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_RunStrafe.MSS_FoleySound_RunStrafe'"));
	MSS_FoleySound_RunStrafeOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.RunStrafe")),
			MSS_FoleySound_RunStrafeOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_TumbleOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Tumble.MSS_FoleySound_Tumble'"));
	MSS_FoleySound_TumbleOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Tumble")),
			MSS_FoleySound_TumbleOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_WalkBackwardsOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_WalkBackwards.MSS_FoleySound_WalkBackwards'"));
	MSS_FoleySound_WalkBackwardsOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.WalkBackwds")),
			MSS_FoleySound_WalkBackwardsOfPath.Object.Get());
	}

	if (const ConstructorHelpers::FObjectFinder<USoundBase> MSS_FoleySound_SlideOfPath(
	TEXT("/Script/MetasoundEngine.MetaSoundSource'/Game/Audio/Foley/MetaSounds/Presets/MSS_FoleySound_Looping_Slide.MSS_FoleySound_Looping_Slide'"));
	MSS_FoleySound_SlideOfPath.Succeeded())
	{
		FoleyAudioAssets.Add(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Slide.Loop")),
			MSS_FoleySound_SlideOfPath.Object.Get());
	}

}

USoundBase* UDataAsset_FoleyAudioBank::GetFoleyAudioAssetByTag(const FGameplayTag& Event, bool& bSuccess) const
{
	if (const TObjectPtr<USoundBase>* FoundAsset = FoleyAudioAssets.Find(Event))
	{
		bSuccess = true;
		return *FoundAsset;
	}
	bSuccess = false;
	return nullptr;
}
