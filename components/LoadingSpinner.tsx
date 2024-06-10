import React from 'react'
import CircuitIcon from '@/public/img/circuit-icon.svg';

export default function LoadingAnimation() {
    return (
        <div className="flex justify-center items-center p-4">
            <div className="animate-pulse">
                <CircuitIcon height={26} />
            </div>
        </div>
    );
};
