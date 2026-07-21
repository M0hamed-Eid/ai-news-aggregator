'use client';

interface DepthGaugeProps {
  depth: number;
}

export default function DepthGauge({ depth }: DepthGaugeProps) {
  return (
    <div className="depth-gauge" title={`Technical depth: ${depth}/5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className={`bar ${i <= depth ? 'active' : ''}`}
        />
      ))}
    </div>
  );
}