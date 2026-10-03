#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "TraversalComponent.generated.h"

UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class UMWSAMPLEPREVIEW_API UTraversalComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UTraversalComponent();

protected:
	virtual void BeginPlay() override;

public:
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
	                           FActorComponentTickFunction* ThisTickFunction) override;

public:
	//跑酷计算常量。
	UPROPERTY(BlueprintReadWrite, EditDefaultsOnly, Category = "默认")
	double MinLedgeWidth;

	UPROPERTY(BlueprintReadWrite, EditDefaultsOnly, Category = "默认")
	bool bPersistentShowTrace;

	UPROPERTY(BlueprintReadWrite, EditDefaultsOnly, Category = "默认")
	bool bShowTrace;

	UPROPERTY(BlueprintReadWrite, EditDefaultsOnly, Category = "默认")
	bool bTraceComplex;

	UPROPERTY(BlueprintReadWrite, EditDefaultsOnly, Category = "默认")
	double MinFrontLedgeDepth;
};
