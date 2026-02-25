document.addEventListener('DOMContentLoaded', () => {
    const fluidContainers = document.querySelectorAll('.ambient-fluid, .ambient-fluid-bg');
    if (!fluidContainers.length) return;

    fluidContainers.forEach(container => {
        // Create the individual canvas for this container
        const canvas = document.createElement('canvas');
        canvas.className = 'fluid-canvas';

        // Inject the canvas at the very start of the container
        container.insertBefore(canvas, container.firstChild);

        // Start hidden to mask the initial random splash from the library
        canvas.style.opacity = '0';
        canvas.style.transition = 'opacity 1.5s ease-in-out';

        // Check if this specific container is requesting heavy GPU graphics
        const isHighFidelity = container.getAttribute('data-high-fidelity') === 'true';

        // Check if the container should have a solid background (not transparent)
        const isTransparent = container.getAttribute('data-transparent') !== 'false';

        // Allow custom background color via hex string (e.g., data-bg-color="#ffffff")
        let backColor = { r: 0, g: 0, b: 0 }; // Default to black
        const bgColorAttr = container.getAttribute('data-bg-color');
        if (bgColorAttr && /^#[0-9a-fA-F]{6}$/.test(bgColorAttr)) {
            backColor = {
                r: parseInt(bgColorAttr.substring(1, 3), 16),
                g: parseInt(bgColorAttr.substring(3, 5), 16),
                b: parseInt(bgColorAttr.substring(5, 7), 16)
            };
        }

        // MUST DISABLE NATIVE TOUCH HANDLERS on webgl-fluid!
        // webgl-fluid's native touch listeners use absolute pageX/pageY coordinates which are
        // completely incorrect for non-fullscreen canvases, making fluid draw far outside the container.
        const originalAddEventListener = canvas.addEventListener;
        canvas.addEventListener = function (type, listener, options) {
            // Intercept and discard touch binding requests from the library
            if (type === 'touchstart' || type === 'touchmove') return;
            originalAddEventListener.call(canvas, type, listener, options);
        };

        // Initialize Independent WebGL Fluid Simulation
        // ----------------------------------------------------------------------------------
        WebGLFluid(canvas, {
            IMMEDIATE: true,
            TRIGGER: 'hover',
            SIM_RESOLUTION: isHighFidelity ? 128 : 32, // High fidelity runs 128 res, standard runs fast 32
            DYE_RESOLUTION: isHighFidelity ? 512 : 256,
            CAPTURE_RESOLUTION: 128,
            DENSITY_DISSIPATION: 1.5,
            VELOCITY_DISSIPATION: 1.5,
            PRESSURE: 0.1,
            PRESSURE_ITERATIONS: isHighFidelity ? 15 : 5, // High fidelity gets more accurate physics
            CURL: 0,
            SPLAT_RADIUS: 0.3,
            SPLAT_FORCE: 6000,
            SHADING: isHighFidelity,    // Effects are ON for high-fidelity only
            COLORFUL: true,
            COLOR_UPDATE_SPEED: 3,
            PAUSED: false,
            BACK_COLOR: backColor,
            TRANSPARENT: isTransparent,
            BLOOM: isHighFidelity,      // Effects are ON for high-fidelity only
            BLOOM_ITERATIONS: 8,
            BLOOM_RESOLUTION: 256,
            BLOOM_INTENSITY: 0.3,
            BLOOM_THRESHOLD: 0.6,
            BLOOM_SOFT_KNEE: 0.7,
            SUNRAYS: isHighFidelity,    // Effects are ON for high-fidelity only
            SUNRAYS_RESOLUTION: 196,
            SUNRAYS_WEIGHT: 1.0,
        });

        // Restore native canvas listener capability immediately after initialization
        canvas.addEventListener = originalAddEventListener;

        // Fade the canvas in after the initial splash dissipates
        setTimeout(() => {
            canvas.style.opacity = '1';
        }, 1);

        // If this is the full-screen background, we want it to react to the mouse anywhere on the page
        const isFullScreenBg = container.classList.contains('ambient-fluid-bg');
        const listenerTarget = isFullScreenBg ? window : container;

        // Forward mouse events from the target to the canvas. 
        // This ensures the fluid reacts even when the user is hovering over 
        // text, buttons, or links that sit visually above the canvas.
        listenerTarget.addEventListener('mousemove', (e) => {
            // If the element (or its parent) has data-no-fluid="true", ignore the event entirely
            if (e.target.closest && e.target.closest('[data-no-fluid="true"]')) return;

            if (e.target !== canvas) {
                // webgl-fluid reads offsetX/offsetY. We must explicitly inject them 
                // because synthetic events fail to populate local node coordinates correctly.
                const proxyEvent = new Event('mousemove');
                const rect = canvas.getBoundingClientRect();
                proxyEvent.offsetX = e.clientX - rect.left;
                proxyEvent.offsetY = e.clientY - rect.top;
                canvas.dispatchEvent(proxyEvent);
            }
        });

        const handleTouch = (e) => {
            if (!e.target.closest) return;

            const dragNode = e.target.closest('[data-fluid-drag="true"]') || (container.getAttribute('data-fluid-drag') === 'true' ? container : null);
            const noFluidNode = e.target.closest('[data-no-fluid="true"]');

            if (noFluidNode) {
                // If there's no drag flag anywhere, or if the no-fluid flag is on a child element
                // strictly inside the drag container (e.g. dragging a button inside a dragged div), block the fluid.
                // However, if they are on the exact same element, the drag flag overrides the no-fluid flag on mobile.
                if (!dragNode || (dragNode !== noFluidNode && dragNode.contains(noFluidNode))) {
                    return;
                }
            }

            // On mobile, explicitly require the drag flag to interact with fluid!
            if (!dragNode) return;

            // PREVENT CROSS-TALK:
            // Since touches bubble up to window (where the fullscreen bg listens),
            // a touch on the squircle triggers BOTH the squircle's handleTouch AND window's handleTouch!
            // If we are currently handling the window listener (isFullScreenBg) BUT the touch 
            // natively originated inside a localized fluid container (e.g. the squircle), skip it!
            const isInsideLocalFluidBox = e.target.closest('.ambient-fluid:not(.ambient-fluid-bg)');
            if (isFullScreenBg && isInsideLocalFluidBox) return;

            if (e.touches.length > 0) {
                const touch = e.touches[0];
                const proxyEvent = new Event('mousemove');
                const rect = canvas.getBoundingClientRect();

                // CRITICAL: webgl-fluid relies strictly on offsetX and offsetY for local mapping!
                proxyEvent.offsetX = touch.clientX - rect.left;
                proxyEvent.offsetY = touch.clientY - rect.top;

                canvas.dispatchEvent(proxyEvent);
            }
        };

        listenerTarget.addEventListener('touchstart', handleTouch, { passive: true });
        listenerTarget.addEventListener('touchmove', handleTouch, { passive: false });
    });
});
