// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"

#include "Animation/AnimNotifies/AnimNotify.h"

#include "CommonGameplay/Foley/FoleyEventsComponent.h"

#include "AnimNotify_FoleyEvent.generated.h"

/**
 *
 */
UCLASS(Blueprintable)
class UMWSAMPLEPREVIEW_API UAnimNotify_FoleyEvent : public UAnimNotify
{
	GENERATED_BODY()

public:
	UAnimNotify_FoleyEvent();
	virtual void Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference) override;
	virtual FString GetNotifyName_Implementation() const override;
private:
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Debug",meta=(AllowPrivateAccess="true"))
	FLinearColor VisLogDebugColor;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Debug",meta=(AllowPrivateAccess="true"))
	FString VisLogDebugText;

public:
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag Event;

	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TEnumAsByte<EFoleyEventSide> Side;

	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	double VolumeMultiplier;

	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	double PitchMultiplier;

	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TObjectPtr<UDataAsset_FoleyAudioBank> DefaultBank;

	UFUNCTION(BlueprintCallable)
	void SetVolumeMultiplier(float InVolumeMultiplier)
	{
		VolumeMultiplier = InVolumeMultiplier;
	}
};
