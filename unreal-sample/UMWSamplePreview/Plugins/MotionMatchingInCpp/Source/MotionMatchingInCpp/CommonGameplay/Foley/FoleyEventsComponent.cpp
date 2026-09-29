// Fill out your copyright notice in the Description page of Project Settings.


#include "FoleyEventsComponent.h"
#include "DataAsset_FoleyAudioBank.h"
#include "Interface_FoleyAudioBank.h"

#include "Components/MeshComponent.h"

#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"

#include "UObject/ConstructorHelpers.h"



// Sets default values for this component's properties
UFoleyEventsComponent::UFoleyEventsComponent()
{
	// Set this component to be initialized when the game starts, and to be ticked every frame.  You can turn these features
	// off to improve performance if you don't need them.
	PrimaryComponentTick.bCanEverTick = true;
	
	if (const ConstructorHelpers::FObjectFinder<UDataAsset_FoleyAudioBank> FoleyEventBankOfPath(
		TEXT("/Script/MotionMatchingInCpp.DataAsset_FoleyAudioBank'/MotionMatchingInCpp/Audio/Foley/DS_DefaultFoleyEventAudioBank.DS_DefaultFoleyEventAudioBank'"));
		FoleyEventBankOfPath.Succeeded())
	{
		FoleyEventBank = FoleyEventBankOfPath.Object.Get();
	}
	VisLogDebugColor = FLinearColor(0.003123f,0.918403f,0.055572f,0.941177f);
}


// Called when the game starts
void UFoleyEventsComponent::BeginPlay()
{
	Super::BeginPlay();

	// ...
	
}


// Called every frame
void UFoleyEventsComponent::TickComponent(float DeltaTime, ELevelTick TickType,
                                          FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// ...
}

bool UFoleyEventsComponent::CanPlayFoley() const
{
	if (!FoleyEventBank)
	{
		return true;
	}
	
	if (FoleyEventBank->GetClass()->ImplementsInterface(UInterface_FoleyAudioBank::StaticClass()))
	{
		return IInterface_FoleyAudioBank::Execute_CanPlayFoleyEvent(FoleyEventBank);
	}
	
	return true;
}

void UFoleyEventsComponent::TriggerVisLog(FFoleyEventParams Params)
{
	UMeshComponent* MeshComponent = Cast<UMeshComponent>
	(GetOwner()->GetComponentByClass(UMeshComponent::StaticClass()));
	if (!MeshComponent)
	{
		return;
	}
	FVector CenterLocation = FVector::ZeroVector;
	switch (Params.EventSide)
	{
	case None:
		CenterLocation = MeshComponent->GetComponentLocation();
		break;
	case Left:
		CenterLocation = MeshComponent->GetSocketLocation(FName("foot_l"));
		break;
	case Right:
		CenterLocation = MeshComponent->GetSocketLocation(FName("foot_r"));
		break;
	}
	if (UKismetSystemLibrary::GetConsoleVariableBoolValue(FString("DDCvar.DrawVisLogShapesForFoleySounds")))
	{
		UKismetSystemLibrary::DrawDebugSphere(MeshComponent,CenterLocation,
			1.0f,12,VisLogDebugColor,0.25f,1.0f,
			EDrawDebugSceneDepthPriorityGroup::World);
	}
}

UAudioComponent* UFoleyEventsComponent::PlayFoleyEvent(FGameplayTag Event, FFoleyEventParams Params)
{
	if (!IsValid(this))
	{
		return nullptr;
	}

	AActor* Owner = GetOwner();
	if (!IsValid(Owner))
	{
		return nullptr;
	}
	
	if (!FoleyEventBank)
	{
		return nullptr;
	}
	bool bPlayFoleySuccess = CanPlayFoley();
	const USoundBase* FoleySound = FoleyEventBank->GetFoleyAudioAssetByTag(Event,bPlayFoleySuccess);
	if (!FoleySound)
	{
		return nullptr;
	}

	UAudioComponent* FoleyAudioComponent = UGameplayStatics::SpawnSoundAttached(const_cast<USoundBase*>(FoleySound),
		Owner->GetRootComponent(),
		FName("None"),
		FVector::ZeroVector, FRotator::ZeroRotator,
		EAttachLocation::KeepRelativeOffset,
		false,
		Params.Volume, Params.Pitch, 0.0f,
		nullptr, nullptr,
		true);
	
	TriggerVisLog(Params);
	return FoleyAudioComponent;
}

