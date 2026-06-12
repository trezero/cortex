/**
 * OnboardingFlow - Welcome component shown when profile.onboarding_completed is false.
 *
 * Displays a simple welcome message and prompts the user to start chatting.
 * The actual onboarding interview is handled by the ChatAgent system prompt,
 * which detects onboarding_completed=false and guides the conversation.
 */

import { MessageCircle, Sparkles, ArrowRight } from "lucide-react";

interface OnboardingFlowProps {
  onStartChat: () => void;
}

export function OnboardingFlow({ onStartChat }: OnboardingFlowProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center space-y-6">
      {/* Icon */}
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
          <Sparkles className="w-8 h-8 text-cyan-400" />
        </div>
        <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center">
          <MessageCircle className="w-3.5 h-3.5 text-purple-400" />
        </div>
      </div>

      {/* Welcome message */}
      <div className="max-w-md space-y-3">
        <h2 className="text-xl font-semibold text-gray-100">Welcome to Cortex</h2>
        <p className="text-sm text-gray-400 leading-relaxed">
          I'm your AI project advisor. I can help you prioritize work, find synergies
          between projects, and stay focused on what matters most.
        </p>
        <p className="text-sm text-gray-500 leading-relaxed">
          Start a conversation and I'll get to know your goals and working style
          so I can provide personalized recommendations.
        </p>
      </div>

      {/* Start button */}
      <button
        type="button"
        onClick={onStartChat}
        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-sm font-medium hover:bg-cyan-500/25 transition-colors group"
      >
        <span>Start Chatting</span>
        <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
      </button>
    </div>
  );
}
