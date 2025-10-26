import React from 'react';

/**
 * Logo Component - REBEL logo from provided image
 */
function Logo({ className = '', size = 'default' }) {
  const sizeClasses = {
    small: 'h-6',
    default: 'h-8',
    large: 'h-12',
    xlarge: 'h-16'
  };

  return (
    <div className={`${className}`}>
      <img 
        src="https://i.imgur.com/96NYtWC.png" 
        alt="REBEL" 
        className={`${sizeClasses[size]} w-auto`}
      />
    </div>
  );
}

export default Logo;