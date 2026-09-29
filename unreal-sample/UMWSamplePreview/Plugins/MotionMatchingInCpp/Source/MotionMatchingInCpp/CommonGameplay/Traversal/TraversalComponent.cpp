#include "TraversalComponent.h"

UTraversalComponent::UTraversalComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	
	MinLedgeWidth = 30.0f;
	bPersistentShowTrace = false;
	bShowTrace = false;
	bTraceComplex = true;
	MinFrontLedgeDepth = 37.522631;
}

void UTraversalComponent::BeginPlay()
{
	Super::BeginPlay();
}

void UTraversalComponent::TickComponent(float DeltaTime, ELevelTick TickType,
                                        FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
}

