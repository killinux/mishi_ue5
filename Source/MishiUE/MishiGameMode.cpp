#include "MishiGameMode.h"
#include "MishiCameraPawn.h"
#include "MishiPlayerController.h"

AMishiGameMode::AMishiGameMode()
{
	DefaultPawnClass = AMishiCameraPawn::StaticClass();
	PlayerControllerClass = AMishiPlayerController::StaticClass();
}
