// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
#include "DataAsset_FoleyAudioBank.generated.h"

class USoundBase;
/**
 *
 */
UCLASS(Blueprintable,BlueprintType)
class UMWSAMPLEPREVIEW_API UDataAsset_FoleyAudioBank : public UDataAsset
{
	GENERATED_BODY()
public:
	UDataAsset_FoleyAudioBank();

	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="资产")
	TMap<FGameplayTag,TObjectPtr<USoundBase>> FoleyAudioAssets;

	UFUNCTION(BlueprintCallable,BlueprintPure)
	USoundBase* GetFoleyAudioAssetByTag(const FGameplayTag& Event,bool& bSuccess) const;
};
