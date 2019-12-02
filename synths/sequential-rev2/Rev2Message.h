#pragma once

#include "JuceHeader.h"

namespace midikraft {

	class Rev2Message
	{
	public:
		Rev2Message();
		virtual ~Rev2Message();

		bool addMessage(MidiMessage const &message);

		int nrpnController() const;
		int nrpnValue() const;

		std::string getName() const;

	private:
		int nrpn_number_msb_;
		int nrpn_number_lsb_;
		int nrpn_value_msb_;
		int nrpn_value_lsb_;

		JUCE_LEAK_DETECTOR(Rev2Message)
	};

}
