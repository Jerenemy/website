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
                const mouseEvent = new MouseEvent('mousemove', {
                    clientX: e.clientX,
                    clientY: e.clientY,
                    bubbles: false,
                    cancelable: true,
                    view: window
                });
                canvas.dispatchEvent(mouseEvent);
            }
        });

        listenerTarget.addEventListener('touchmove', (e) => {
            // If the element (or its parent) has data-no-fluid="true", ignore the event entirely
            if (e.target.closest && e.target.closest('[data-no-fluid="true"]')) return;

            if (e.target !== canvas && e.touches.length > 0) {
                const touch = e.touches[0];
                const touchEvent = new TouchEvent('touchmove', {
                    changedTouches: [new Touch({
                        identifier: touch.identifier,
                        target: canvas,
                        clientX: touch.clientX,
                        clientY: touch.clientY,
                        pageX: touch.pageX,
                        pageY: touch.pageY,
                    })],
                    touches: e.touches,
                    bubbles: false,
                    cancelable: true,
                    view: window
                });
                canvas.dispatchEvent(touchEvent);
            }
        }, { passive: true });
    });
});
