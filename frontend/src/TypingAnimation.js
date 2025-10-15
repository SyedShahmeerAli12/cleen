import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

const TypingAnimation = ({ text, speed = 30, onComplete }) => {
  const [displayedText, setDisplayedText] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setDisplayedText(prev => prev + text[currentIndex]);
        setCurrentIndex(prev => prev + 1);
      }, speed);

      return () => clearTimeout(timeout);
    } else if (onComplete) {
      onComplete();
    }
  }, [currentIndex, text, speed, onComplete]);

  // Reset when text changes
  useEffect(() => {
    setDisplayedText('');
    setCurrentIndex(0);
  }, [text]);

  return (
    <div className="prose prose-sm max-w-none">
      {displayedText.split('\n').map((line, lineIndex) => {
        let formattedLine = line;
        
        // Headers ### Header (check first)
        if (line.trim().startsWith('### ')) {
          formattedLine = `<h3 class="text-lg font-semibold mb-3 text-gray-800 border-b border-gray-200 pb-1">${line.trim().substring(4)}</h3>`;
        }
        // Headers ## Header
        else if (line.trim().startsWith('## ')) {
          formattedLine = `<h2 class="text-xl font-bold mb-3 text-gray-900">${line.trim().substring(3)}</h2>`;
        }
        // Headers # Header
        else if (line.trim().startsWith('# ')) {
          formattedLine = `<h1 class="text-2xl font-bold mb-4 text-gray-900">${line.trim().substring(2)}</h1>`;
        }
        // Bullet points * item
        else if (line.trim().startsWith('* ')) {
          formattedLine = `<div class="flex items-start mb-2"><span class="mr-2 text-primary-500 font-bold">•</span><span>${line.trim().substring(2)}</span></div>`;
        }
        // Numbered lists 1. item
        else if (/^\d+\.\s/.test(line.trim())) {
          formattedLine = `<div class="flex items-start mb-2"><span class="mr-2 text-primary-500 font-bold">${line.trim().split('.')[0]}.</span><span>${line.trim().substring(line.trim().indexOf(' ') + 1)}</span></div>`;
        }
        // Bold text **text** (do this last)
        else {
          formattedLine = formattedLine.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-800">$1</strong>');
        }
        
        return (
          <div 
            key={lineIndex} 
            dangerouslySetInnerHTML={{ __html: formattedLine }}
          />
        );
      })}
      
      {/* Typing cursor */}
      {currentIndex < text.length && (
        <motion.span
          className="inline-block w-0.5 h-4 bg-primary-500 ml-1"
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
        />
      )}
    </div>
  );
};

export default TypingAnimation;
