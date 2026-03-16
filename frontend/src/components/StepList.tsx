import React from 'react';
import type { Step } from '../types';
import { motion } from 'framer-motion';

interface StepListProps {
  steps: Step[];
  currentStepIndex: number;
  onStepClick: (index: number) => void;
}

const StepList: React.FC<StepListProps> = ({ steps, currentStepIndex, onStepClick }) => {
  return (
    <div className="w-full max-w-4xl mt-8">
      <div className="flex flex-col gap-4">
        {steps.map((step, index) => {
          const isActive = index === currentStepIndex;
          return (
            <motion.div
              key={step.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
              onClick={() => onStepClick(index)}
              className={`p-4 rounded-lg cursor-pointer transition-all duration-300 border ${
                isActive
                  ? 'bg-[#FF6A00]/10 border-[#FF6A00] shadow-[0_0_15px_rgba(255,106,0,0.2)]'
                  : 'bg-zinc-900/50 border-zinc-800 hover:bg-zinc-800'
              }`}
            >
              <div className="flex items-center gap-4">
                <div
                  className={`flex items-center justify-center w-8 h-8 rounded-full font-bold text-sm ${
                    isActive ? 'bg-[#FF6A00] text-white' : 'bg-zinc-700 text-zinc-400'
                  }`}
                >
                  {index + 1}
                </div>
                <div className="flex-1">
                  <h3 className={`font-semibold text-lg ${isActive ? 'text-white' : 'text-zinc-400'}`}>
                    {step.title}
                  </h3>
                  <p className="text-sm text-zinc-500 line-clamp-1">{step.description}</p>
                </div>
                {step.highlight && (
                  <div className="text-xs text-[#FF6A00] font-mono bg-[#FF6A00]/10 px-2 py-1 rounded">
                    {step.highlight}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

export default StepList;
