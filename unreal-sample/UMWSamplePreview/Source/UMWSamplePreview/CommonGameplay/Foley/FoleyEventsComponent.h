// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "FoleyEventsComponent.generated.h"


class UAudioComponent;
struct FGameplayTag;
class UDataAsset_FoleyAudioBank;


UENUM(BlueprintType)
enum EFoleyEventSide
{
	None,
	Left,
	Right
};

USTRUCT(BlueprintType)
struct FFoleyEventParams
{
	GENERATED_BODY()
	
	[[nodiscard]] FFoleyEventParams():
		EventSide(EFoleyEventSide::None),
		Volume(1.0f),
		Pitch(1.0f)
	{
	}
	
	[[nodiscard]] FFoleyEventParams(const TEnumAsByte<EFoleyEventSide>& EventSide, const float Volume,
		const float Pitch)
		: EventSide(EventSide),
		  Volume(Volume),
		  Pitch(Pitch)
	{
	}
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TEnumAsByte<EFoleyEventSide> EventSide;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	float Volume;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	float Pitch;
};

UCLASS(Blueprintable,ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class UMWSAMPLEPREVIEW_API UFoleyEventsComponent : public UActorComponent
{
	GENERATED_BODY()

public: 
	// Sets default values for this component's properties
	UFoleyEventsComponent();

protected:
	// Called when the game starts
	virtual void BeginPlay() override;

public:
	// Called every frame
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
	                           FActorComponentTickFunction* ThisTickFunction) override;
	
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Debug")
	FString VisLogDebugText;
	
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Debug")
	FLinearColor VisLogDebugColor;
	
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Debug")
	TObjectPtr<UDataAsset_FoleyAudioBank> FoleyEventBank;
	
private:
	UFUNCTION(BlueprintCallable,BlueprintPure)
	bool CanPlayFoley() const;
	
	UFUNCTION(BlueprintCallable)
	void TriggerVisLog(FFoleyEventParams Params);
	
public:
	UFUNCTION(BlueprintCallable)
	UAudioComponent* PlayFoleyEvent(FGameplayTag Event, FFoleyEventParams Params);
};
