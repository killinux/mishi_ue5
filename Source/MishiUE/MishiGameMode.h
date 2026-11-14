// The game mode of every Mishi level: the orbit camera as the pawn, the Mishi controller (input + panel).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MishiGameMode.generated.h"

UCLASS()
class MISHIUE_API AMishiGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMishiGameMode();
};
