// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Runtime/Engine/Classes/Components/ActorComponent.h"
#include "PreCMCTick.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnPreCMCTickSignature);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class UMWSAMPLEPREVIEW_API UPreCMCTick : public UActorComponent
{
	GENERATED_BODY()

public:
	// Sets default values for this component's properties
	UPreCMCTick();

	FOnPreCMCTickSignature OnPreCMCTick;
public:
	// Called every frame
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
	                           FActorComponentTickFunction* ThisTickFunction) override;
};
