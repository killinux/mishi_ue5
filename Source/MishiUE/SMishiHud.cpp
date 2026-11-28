#include "SMishiHud.h"
#include "MishiCameraPawn.h"
#include "MishiCouple.h"
#include "MishiPlayerController.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

// The labels are written as \u escapes so the sources stay ASCII whatever code page the compiler reads them in.
#define MISHI_TEXT(S) FText::FromString(FString(TEXT(S)))

namespace
{
	FSlateFontInfo Font(int32 Size) { return FCoreStyle::GetDefaultFontStyle("Regular", Size); }
	const FLinearColor ColorOn(0.95f, 0.50f, 0.32f, 1.f);
	const FLinearColor ColorOff(0.16f, 0.16f, 0.19f, 0.9f);
}

AMishiCouple* SMishiHud::Couple() const
{
	return Owner.IsValid() ? Owner->GetCouple() : nullptr;
}

AMishiCameraPawn* SMishiHud::Cam() const
{
	return Owner.IsValid() ? Owner->GetCam() : nullptr;
}

TSharedRef<SWidget> SMishiHud::Button(TAttribute<FText> Label, TFunction<void()> OnClick, TFunction<bool()> IsOn, float Width)
{
	// (at least Width, and as wide as its label: a showcase's "zhan dou zhan zi" lost its fourth character to a fixed width)
	return SNew(SBox)
		.MinDesiredWidth(Width)
		.HeightOverride(34.f)
		[
			SNew(SButton)
			.IsFocusable(false)
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			.ButtonColorAndOpacity_Lambda([IsOn]() { return FSlateColor(IsOn && IsOn() ? ColorOn : ColorOff); })
			.OnClicked_Lambda([OnClick]() { if (OnClick) OnClick(); return FReply::Handled(); })
			[
				SNew(STextBlock)
				.Font(Font(13))
				.ColorAndOpacity(FLinearColor::White)
				.Text(Label)
			]
		];
}

void SMishiHud::Construct(const FArguments& InArgs)
{
	Owner = InArgs._Owner;
	SetVisibility(EVisibility::SelfHitTestInvisible);

	// (a wrap box: a showcase's nine actions, the switches and the camera presets are wider than a 1600 px window)
	TSharedRef<SWrapBox> Bar = SNew(SWrapBox).UseAllottedSize(true).HAlign(HAlign_Center);
	// a button per phase of the slice (the eros mode's four, a showcase's actions under their own names): those the slice has
	for (int32 I = 0; I < 10; ++I)
	{
		TSharedRef<SWidget> B =
			// "jie duan N" unless the slice names it
			Button(TAttribute<FText>::CreateLambda([this, I]()
				{
					const AMishiCouple* C = Couple();
					if (C && C->IsReady() && C->Slice().Phases.IsValidIndex(I) && !C->Slice().Phases[I].Label.IsEmpty())
						return FText::FromString(C->Slice().Phases[I].Label);
					return FText::Format(MISHI_TEXT("\u9636\u6BB5 {0}"), FText::AsNumber(I + 1));
				}),
				[this, I]() { if (AMishiCouple* C = Couple()) C->GoPhase(I); },
				[this, I]() { const AMishiCouple* C = Couple(); return C && C->CurrentPhase() == I; });
		B->SetVisibility(TAttribute<EVisibility>::CreateLambda([this, I]()
		{
			const AMishiCouple* C = Couple();
			const int32 N = C && C->IsReady() ? C->Slice().Phases.Num() : 4;
			return I < N ? EVisibility::Visible : EVisibility::Collapsed;
		}));
		Bar->AddSlot().Padding(3.f)[B];
	}
	// what only a couple's scene has: him, the blush
	const TAttribute<EVisibility> CoupleOnly = TAttribute<EVisibility>::CreateLambda([this]()
	{
		const AMishiCouple* C = Couple();
		return !C || !C->IsReady() || C->Slice().bMale ? EVisibility::Visible : EVisibility::Collapsed;
	});
	Bar->AddSlot().Padding(FMargin(14.f, 3.f, 3.f, 3.f))
	[
		// "zi dong: kai / guan"
		Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
				return C && C->bAuto ? MISHI_TEXT("\u81EA\u52A8\uFF1A\u5F00") : MISHI_TEXT("\u81EA\u52A8\uFF1A\u5173"); }),
			[this]() { if (AMishiCouple* C = Couple()) C->bAuto = !C->bAuto; },
			[this]() { const AMishiCouple* C = Couple(); return C && C->bAuto; }, 96.f)
	];
	Bar->AddSlot().Padding(3.f)
	[
		// "yu yin: ri / ying / guan"
		Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
				const int32 L = C ? C->VoiceLanguage : 0;
				return L == 1 ? MISHI_TEXT("\u8BED\u97F3\uFF1A\u65E5") : L == 2 ? MISHI_TEXT("\u8BED\u97F3\uFF1A\u82F1") : MISHI_TEXT("\u8BED\u97F3\uFF1A\u5173"); }),
			[this]() { if (AMishiCouple* C = Couple()) C->VoiceLanguage = (C->VoiceLanguage + 1) % 3; }, nullptr, 96.f)
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(CoupleOnly)
		[
			// "nan xing: xian shi / yin cang" - him: there or hidden (key M)
			Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
					return C && !C->bShowHim ? MISHI_TEXT("\u7537\u6027\uFF1A\u9690\u85CF") : MISHI_TEXT("\u7537\u6027\uFF1A\u663E\u793A"); }),
				[this]() { if (AMishiCouple* C = Couple()) C->SetShowHim(!C->bShowHim); },
				[this]() { const AMishiCouple* C = Couple(); return C && C->bShowHim; }, 112.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(CoupleOnly)
		[
			// "hua fa: pi fu / jian ying" - how he is drawn while he is there: his skin, the game's flat silhouette (key K)
			Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
					return C && C->HisShownStyle == 1 ? MISHI_TEXT("\u753B\u6CD5\uFF1A\u526A\u5F71") : MISHI_TEXT("\u753B\u6CD5\uFF1A\u76AE\u80A4"); }),
				[this]() { if (AMishiCouple* C = Couple()) { if (C->bShowHim) C->SetHisStyle(1 - C->HisShownStyle); } }, nullptr, 112.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		// "yin xiao" - the parts' sound loops
		Button(MISHI_TEXT("\u97F3\u6548"),
			[this]() { if (AMishiCouple* C = Couple()) C->SetSfx(!C->bSfx); },
			[this]() { const AMishiCouple* C = Couple(); return C && C->bSfx; }, 64.f)
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(CoupleOnly)
		[
			// "chao hong" - sweat and blush following the phase
			Button(MISHI_TEXT("\u6F6E\u7EA2"),
				[this]() { if (AMishiCouple* C = Couple()) C->bSkinState = !C->bSkinState; },
				[this]() { const AMishiCouple* C = Couple(); return C && C->bSkinState; }, 64.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(CoupleOnly)
		[
			// "chu han: kai / guan" - sweat on its own (key G): off, the skin stays dry whatever the phase
			Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
					return C && !C->bSweat ? MISHI_TEXT("\u51FA\u6C57\uFF1A\u5173") : MISHI_TEXT("\u51FA\u6C57\uFF1A\u5F00"); }),
				[this]() { if (AMishiCouple* C = Couple()) C->bSweat = !C->bSweat; },
				[this]() { const AMishiCouple* C = Couple(); return C && C->bSweat && C->bSkinState; }, 96.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		// "pi fu: v0.2 / v0.1 / yuan ban" - which skin is shown (key N): a skin pack's maps drawn into the bodies' own layout,
		// the tiled relief and beads alone, the game's own materials
		Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
				const int32 V = C ? C->SkinVersion : 2;
				return V >= 2 ? MISHI_TEXT("\u76AE\u80A4\uFF1Av0.2") : V == 1 ? MISHI_TEXT("\u76AE\u80A4\uFF1Av0.1") : MISHI_TEXT("\u76AE\u80A4\uFF1A\u539F\u7248"); }),
			[this]() { if (AMishiCouple* C = Couple()) C->SkinVersion = (C->SkinVersion + 2) % 3; },
			[this]() { const AMishiCouple* C = Couple(); return C && C->SkinVersion >= 2; }, 112.f)
	];
	Bar->AddSlot().Padding(3.f)
	[
		// "te xie: guan / lian / xiong" - a close-up (key F): the orbit rides on her face or her chest and the wheel goes in
		// closer than the game's own orbit lets it
		Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCameraPawn* Cam = Owner.IsValid() ? Owner->GetCam() : nullptr;
				const int32 Which = Cam ? Cam->GetCloseUp() : 0;
				return Which == 1 ? MISHI_TEXT("\u7279\u5199\uFF1A\u8138") : Which == 2 ? MISHI_TEXT("\u7279\u5199\uFF1A\u80F8") : MISHI_TEXT("\u7279\u5199\uFF1A\u5173"); }),
			[this]() { if (AMishiCameraPawn* Cam = Owner.IsValid() ? Owner->GetCam() : nullptr) Cam->SetCloseUp((Cam->GetCloseUp() + 1) % 3); },
			[this]() { const AMishiCameraPawn* Cam = Owner.IsValid() ? Owner->GetCam() : nullptr; return Cam && Cam->GetCloseUp() > 0; }, 100.f)
	];
	// what only a showcase has: the game's own camera for the skills
	const TAttribute<EVisibility> ShowcaseOnly = TAttribute<EVisibility>::CreateLambda([this]()
	{
		const AMishiCouple* C = Couple();
		return C && C->IsReady() && C->Slice().Kind == TEXT("showcase") ? EVisibility::Visible : EVisibility::Collapsed;
	});
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(ShowcaseOnly)
		[
			// "ji neng jing tou: kai / guan" - a skill seen through the game's own camera, or the orbit kept
			Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCameraPawn* P = Cam();
					return P && P->bSkillCamera ? MISHI_TEXT("技能镜头：开") : MISHI_TEXT("技能镜头：关"); }),
				[this]() { if (AMishiCameraPawn* P = Cam()) P->bSkillCamera = !P->bSkillCamera; },
				[this]() { const AMishiCameraPawn* P = Cam(); return P && P->bSkillCamera; }, 128.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(TAttribute<EVisibility>::CreateLambda([this]()
			{ const AMishiCouple* C = Couple(); return C && C->IsReady() && C->HasSprings() ? EVisibility::Visible : EVisibility::Collapsed; }))
		[
			// "wu li" - hair, chains and skirt swing over the clips
			Button(MISHI_TEXT("物理"),
				[this]() { if (AMishiCouple* C = Couple()) C->bSprings = !C->bSprings; },
				[this]() { const AMishiCouple* C = Couple(); return C && C->bSprings; }, 64.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(TAttribute<EVisibility>::CreateLambda([this]()
			{ const AMishiCouple* C = Couple(); return C && C->IsReady() && C->HasFx() ? EVisibility::Visible : EVisibility::Collapsed; }))
		[
			// "te xiao" - the skills' effects
			Button(MISHI_TEXT("特效"),
				[this]() { if (AMishiCouple* C = Couple()) C->bFx = !C->bFx; },
				[this]() { const AMishiCouple* C = Couple(); return C && C->bFx; }, 64.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(TAttribute<EVisibility>::CreateLambda([this]()
			{ const AMishiCouple* C = Couple(); return C && C->IsReady() && C->HasAura() ? EVisibility::Visible : EVisibility::Collapsed; }))
		[
			// "guang huan: zhan dou / chang kai / guan" - the buff's aura: in battle (the stance, the skills, a hit) as the game
			// has it, on every part, off
			Button(TAttribute<FText>::CreateLambda([this]() { const AMishiCouple* C = Couple();
					return !C || C->AuraMode == 0 ? MISHI_TEXT("光环：关") : C->AuraMode == 1 ? MISHI_TEXT("光环：战斗") : MISHI_TEXT("光环：常开"); }),
				[this]() { if (AMishiCouple* C = Couple()) C->AuraMode = (C->AuraMode + 1) % 3; },
				[this]() { const AMishiCouple* C = Couple(); return C && C->AuraMode > 0; }, 112.f)
		]
	];
	// "hua zhi" - the picture's upscaler: the engine's TSR, or NVIDIA's DLSS where its plugin is installed and the card can
	// (DLAA = its anti-aliasing on the full picture; quality / balanced / performance render 67 / 58 / 50 % of the width);
	// "guang xian chong jian" - DLSS ray reconstruction, one denoiser for Lumen's reflections and shadows
	const bool bDlss = AMishiPlayerController::HasDLSS();
	const bool bDlssRR = bDlss && AMishiPlayerController::HasRayReconstruction();
	Bar->AddSlot().Padding(FMargin(14.f, 3.f, 3.f, 3.f))
	[
		SNew(SBox).Visibility(bDlss ? EVisibility::Visible : EVisibility::Collapsed)
		[
			Button(TAttribute<FText>::CreateLambda([this]()
				{
					switch (Owner.IsValid() ? Owner->GetUpscale() : 0)
					{
					case 1: return MISHI_TEXT("画质：DLAA");
					case 2: return MISHI_TEXT("DLSS 质量");
					case 3: return MISHI_TEXT("DLSS 平衡");
					case 4: return MISHI_TEXT("DLSS 性能");
					default: return MISHI_TEXT("画质：TSR");
					}
				}),
				[this]() { if (Owner.IsValid()) { const bool bRR = Owner->GetRayReconstruction(); Owner->SetUpscale((Owner->GetUpscale() + 1) % 5); Owner->SetRayReconstruction(bRR); } },
				[this]() { return Owner.IsValid() && Owner->GetUpscale() > 0; }, 124.f)
		]
	];
	Bar->AddSlot().Padding(3.f)
	[
		SNew(SBox).Visibility(bDlssRR ? EVisibility::Visible : EVisibility::Collapsed)
		[
			Button(MISHI_TEXT("光线重建"),
				[this]() { if (Owner.IsValid()) Owner->SetRayReconstruction(!Owner->GetRayReconstruction()); },
				[this]() { return Owner.IsValid() && Owner->GetRayReconstruction(); }, 100.f)
		]
	];
	// camera presets: "quan jing", "zheng mian", "ce mian", "fu shi", "te xie", "fu wei"
	struct FPreset { const TCHAR* Label; int32 Kind; };
	const FPreset Presets[] = {
		{TEXT("\u5168\u666F"), 0}, {TEXT("\u6B63\u9762"), 1}, {TEXT("\u4FA7\u9762"), 2}, {TEXT("\u4FEF\u89C6"), 3}, {TEXT("\u7279\u5199"), 4}, {TEXT("\u590D\u4F4D"), 5}};
	for (int32 I = 0; I < UE_ARRAY_COUNT(Presets); ++I)
	{
		const int32 Kind = Presets[I].Kind;
		Bar->AddSlot().Padding(FMargin(I == 0 ? 14.f : 3.f, 3.f, 3.f, 3.f))
		[
			Button(FText::FromString(Presets[I].Label), [this, Kind]()
			{
				AMishiCameraPawn* P = Cam();
				if (!P)
					return;
				const float Z0 = P->DefaultZoom(), Y0 = P->DefaultYaw();
				switch (Kind)
				{
				case 0: P->SetView(Y0, 0.6f, Z0 * 1.8f); break;
				case 1: P->SetView(Y0 + 180.f, 0.55f, Z0 * 1.05f); break;
				case 2: P->SetView(Y0 + 90.f, 0.5f, Z0 * 1.2f); break;
				case 3: P->SetView(Y0, 0.98f, Z0 * 1.1f); break;
				case 4: P->SetView(P->GetYaw(), P->GetY(), Z0 * 0.6f); break;
				default: P->ResetView(); break;
				}
			}, nullptr, 64.f)
		];
	}

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Top)
		.Padding(16.f)
		[
			SNew(STextBlock)
			.Visibility(EVisibility::HitTestInvisible)
			.Font(Font(16))
			.ColorAndOpacity(FLinearColor::White)
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.85f))
			.Text_Lambda([this]()
			{
				const AMishiCouple* C = Couple();
				if (!C || !C->IsReady())
					return FText::FromString(TEXT("Mishi UE5 - no couple in the level (Tools/import_slice.py)"));
				return FText::FromString(FString::Printf(TEXT("%s\n%s  phase %d"), *C->Slice().Title, *C->CurrentPart(), C->CurrentPhase() + 1));
			})
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(120.f, 0.f, 120.f, 92.f))
		[
			SNew(STextBlock)
			.Visibility(EVisibility::HitTestInvisible)
			.Font(Font(20))
			.AutoWrapText(true)
			.Justification(ETextJustify::Center)
			.ColorAndOpacity(FLinearColor(1.f, 0.97f, 0.92f, 1.f))
			.ShadowOffset(FVector2D(1.5f, 1.5f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.9f))
			.Text_Lambda([this]()
			{
				const AMishiCouple* C = Couple();
				return C ? FText::FromString(C->CurrentLine()) : FText::GetEmpty();
			})
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Fill)
		.VAlign(VAlign_Bottom)
		.Padding(12.f)
		[
			SNew(SBorder)
			.BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
			.BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.45f))
			.Padding(6.f)
			[
				Bar
			]
		]
	];
}

#undef MISHI_TEXT
