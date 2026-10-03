// Fill out your copyright notice in the Description page of Project Settings.


#include "BlueprintFunctionLibrary_MotionMatchingHelpers.h"

#include "GameFramework/Pawn.h"

#include "Kismet/KismetSystemLibrary.h"

#include "Templates/SubclassOf.h"


void UBlueprintFunctionLibrary_MotionMatchingHelpers::AddToStringHistoryArray(TArray<FString>& InOutValues,
	const FString& NewValue, int32 MaxHistoryLength)
{
	InOutValues.Insert(NewValue,0);
	if (InOutValues.IsValidIndex(MaxHistoryLength))
	{
		InOutValues.RemoveAt(MaxHistoryLength);
	}
}

TArray<FString> UBlueprintFunctionLibrary_MotionMatchingHelpers::GetObjectNames(const TArray<UObject*> Objects)
{
	TArray<FString> InOutValues;
	for (UObject* const& Object : Objects)
	{
		InOutValues.Add(UKismetSystemLibrary::GetDisplayName(Object));
	}
	return InOutValues;
}

TSubclassOf<APawn> UBlueprintFunctionLibrary_MotionMatchingHelpers::GetPawnClassWithCVAR(
	TArray<TSubclassOf<APawn>>& PawnClasses, TSubclassOf<APawn> DefaultPawnClass)
{
	const int32 CVARValue = UKismetSystemLibrary::GetConsoleVariableIntValue(TEXT("DDCVar.PawnClass"));

	if (!PawnClasses.IsValidIndex(CVARValue))
	{
		return DefaultPawnClass;
	}

	const TSubclassOf<APawn> SelectedPawnClass = PawnClasses[CVARValue];
	return UKismetSystemLibrary::IsValidClass(SelectedPawnClass) ? SelectedPawnClass : DefaultPawnClass;
}

// cpp
TSubclassOf<AActor> UBlueprintFunctionLibrary_MotionMatchingHelpers::GetVisualOverrideWithCVAR(
	TArray<TSubclassOf<AActor>>& VisualOverrides)
{
	const int32 CVARValue = UKismetSystemLibrary::GetConsoleVariableIntValue(TEXT("DDCVar.VisualOverride"));

	if (!VisualOverrides.IsValidIndex(CVARValue))
	{
		return nullptr;
	}

	const TSubclassOf<AActor> SelectedVisualOverride = VisualOverrides[CVARValue];
	return UKismetSystemLibrary::IsValidClass(SelectedVisualOverride) ? SelectedVisualOverride : nullptr;
}
