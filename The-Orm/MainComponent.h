/*
   Copyright (c) 2020 Christof Ruch. All rights reserved.

   Dual licensed: Distributed under Affero GPL license by default, an MIT license is available for purchase
*/

#pragma once

#include "JuceHeader.h"

#include "LogView.h"
#include "MidiLogView.h"
#include "PatchButtonGrid.h"
#include "InsetBox.h"

#include "PatchDatabase.h"
#include "AutoDetection.h"
#include "PropertyEditor.h"
#include "SynthList.h"
#include "LambdaMenuModel.h"
#include "LambdaButtonStrip.h"

#include "PatchView.h"
#include "SettingsView.h"
#include "KeyboardMacroView.h"

#include "Rev2.h"
#include "OB6.h"

class LogViewLogger;

class MainComponent : public Component, private ChangeListener
{
public:
    MainComponent();
    ~MainComponent();

    virtual void resized() override;

private:
	File getAutoCategoryFile() const;
	void aboutBox();

	virtual void changeListenerCallback(ChangeBroadcaster* source) override;

	midikraft::PatchDatabase database_;
	midikraft::AutoDetection autodetector_;
	std::shared_ptr<midikraft::Rev2> rev2_;
	std::shared_ptr<midikraft::OB6> ob6_;

	// The infrastructure for the menu and the short cut keys
	std::unique_ptr<LambdaMenuModel> menuModel_;
	LambdaButtonStrip buttons_;
	ApplicationCommandManager commandManager_;
	MenuBarComponent menuBar_;

	SynthList synthList_;
	TabbedComponent mainTabs_;
	LogView logView_;
	std::unique_ptr<PatchView> patchView_;
	std::unique_ptr<KeyboardMacroView> keyboardView_;
	StretchableLayoutManager stretchableManager_;
	StretchableLayoutResizerBar resizerBar_;
	MidiLogView midiLogView_;
	InsetBox midiLogArea_;
	std::unique_ptr<SettingsView> settingsView_;
	std::unique_ptr<LogViewLogger> logger_;
	std::vector<MidiMessage> currentDownload_;

	InsetBox logArea_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (MainComponent)
};
