// The panel over the view (Slate, no UMG asset): title and part top left, the narration line, and the bar - phases 1-4, auto,
// voice language, him, camera presets - as in the Unity version.
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class AMishiPlayerController;
class AMishiCouple;
class AMishiCameraPawn;

class SMishiHud : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SMishiHud) {}
		SLATE_ARGUMENT(AMishiPlayerController*, Owner)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TWeakObjectPtr<AMishiPlayerController> Owner;

	AMishiCouple* Couple() const;
	AMishiCameraPawn* Cam() const;
	TSharedRef<SWidget> Button(TAttribute<FText> Label, TFunction<void()> OnClick, TFunction<bool()> IsOn = nullptr, float Width = 84.f);
};
