const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the return statement - use a helper function
const oldCode = `    const returnValue = {
      isSharing: state.isSharing,
      stream: state.stream,
      error: state.error,
      tracks: state.tracks,
      startScreenShare,
      stopScreenShare,
      toggleScreenShare,
      replaceTrack,
    };
    return returnValue;
  };
}`;

const newCode = `    return createReturnValue(state, startScreenShare, stopScreenShare, toggleScreenShare, replaceTrack);
  };
}

function createReturnValue(state: ScreenShareState, startScreenShare: UseScreenShareReturn['startScreenShare'], stopScreenShare: UseScreenShareReturn['stopScreenShare'], toggleScreenShare: UseScreenShareReturn['toggleScreenShare'], replaceTrack: UseScreenShareReturn['replaceTrack']): UseScreenShareReturn {
  return {
    isSharing: state.isSharing,
    stream: state.stream,
    error: state.error,
    tracks: state.tracks,
    startScreenShare,
    stopScreenShare,
    toggleScreenShare,
    replaceTrack,
  };
}
`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - helper function');
} else {
  console.log('Old code not found');
}