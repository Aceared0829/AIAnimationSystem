// Fill out your copyright notice in the Description page of Project Settings.


#include "PreCMCTick.h"


// Sets default values for this component's properties
UPreCMCTick::UPreCMCTick()
{
	// Set this component to be initialized when the game starts, and to be ticked every frame.  You can turn these features
	// off to improve performance if you don't need them.
	PrimaryComponentTick.bCanEverTick = true;

	// ...
}


// Called every frame
void UPreCMCTick::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	//每帧调用委托
	OnPreCMCTick.Broadcast();
}

