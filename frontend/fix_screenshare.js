const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Find the early return and the return statement
// Replace:
// if (!isSharing && !stream) return null;
// 
// return (
//   <div ...>
// );

// With:
// return isSharing && stream ? (
//   <div ...>
// ) : null;

const oldCode = `if (!isSharing && !stream) return null;

  return (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>
      {/* Preview Header */}
      <div className={classNames(
        "flex items-center justify-between px-3 py-2 bg-black/80 text-white border-b border-line",
        isMinimized && "px-2 py-1"
      )}>
        <div className="flex items-center gap-2">
          <span className={classNames(
            "flex items-center gap-1.5 text-xs font-medium",
            "text-green-400"
          )}>
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Sharing Screen
          </span>
        </div>
        <div className="flex items-center gap-1">
          {!isMinimized && (
            <button
              onClick={onMinimize}
              className="p-1.5 rounded hover:bg-white/10 transition-colors"
              aria-label="Minimize"
            >
              <Minimize2 className="h-4 w-4" />
            </button>
          )}
          {isMinimized && (
            <button
              onClick={onMaximize}
              className="p-1.5 rounded hover:bg-white/10 transition-colors"
              aria-label="Maximize"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onStop}
            className="p-1.5 rounded hover:bg-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors"
            aria-label="Stop sharing"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Video Preview */}
      <div className={classNames(
        "relative w-full h-full bg-black",
        isMinimized ? "h-20" : "h-full"
      )}>
        {stream && (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="w-full h-full object-cover"
          />
        )}
        {!stream && (
          <div className="absolute inset-0 flex items-center justify-center text-white/50">
            <div className="text-center">
              <MonitorOff className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No screen share active</p>
            </div>
          </div>
        )}
        {!stream && !isMinimized && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <button
              onClick={() => {}}
              className="px-6 py-3 bg-brand text-white rounded-lg font-medium hover:bg-brand-strong transition-colors"
            >
              Start Screen Sharing
            </button>
          </div>
        )}
      </div>
    </div>
  );`;

const newCode = `return isSharing && stream ? (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>
      {/* Preview Header */}
      <div className={classNames(
        "flex items-center justify-between px-3 py-2 bg-black/80 text-white border-b border-line",
        isMinimized && "px-2 py-1"
      )}>
        <div className="flex items-center gap-2">
          <span className={classNames(
            "flex items-center gap-1.5 text-xs font-medium",
            "text-green-400"
          )}>
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Sharing Screen
          </span>
        </div>
        <div className="flex items-center gap-1">
          {!isMinimized && (
            <button
              onClick={onMinimize}
              className="p-1.5 rounded hover:bg-white/10 transition-colors"
              aria-label="Minimize"
            >
              <Minimize2 className="h-4 w-4" />
            </button>
          )}
          {isMinimized && (
            <button
              onClick={onMaximize}
              className="p-1.5 rounded hover:bg-white/10 transition-colors"
              aria-label="Maximize"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onStop}
            className="p-1.5 rounded hover:bg-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors"
            aria-label="Stop sharing"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Video Preview */}
      <div className={classNames(
        "relative w-full h-full bg-black",
        isMinimized ? "h-20" : "h-full"
      )}>
        {stream && (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="w-full h-full object-cover"
          />
        )}
        {!stream && (
          <div className="absolute inset-0 flex items-center justify-center text-white/50">
            <div className="text-center">
              <MonitorOff className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No screen share active</p>
            </div>
          </div>
        )}
        {!stream && !isMinimized && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <button
              onClick={() => {}}
              className="px-6 py-3 bg-brand text-white rounded-lg font-medium hover:bg-brand-strong transition-colors"
            >
              Start Screen Sharing
            </button>
          </div>
        )}
      </div>
    </div>
  ) : null;`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('components/collaboration/ScreenShare.tsx', code);
  console.log('Fixed ScreenShare.tsx');
} else {
  console.log('Old code not found');
}