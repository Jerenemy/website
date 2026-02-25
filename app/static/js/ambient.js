document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('fluid-canvas');
    if (!canvas) return;

    // Start hidden to mask the initial random splash from the library
    canvas.style.opacity = '0';
    canvas.style.transition = 'opacity 1.5s ease-in-out';

    // Initialize WebGL Fluid Simulation
    // These parameters are optimized to look incredibly beautiful (high dye resolution) 
    // but run lag-free (shading off, bloom off, reasonable sim resolution).
    WebGLFluid(canvas, {
        IMMEDIATE: true,
        TRIGGER: 'hover',
        SIM_RESOLUTION: 128,        // Restored to 128 to fix pixelated blockiness and blocky flickering
        DYE_RESOLUTION: 512,        // High resolution for beautiful, smooth colors
        CAPTURE_RESOLUTION: 512,
        DENSITY_DISSIPATION: 1.5,   // Lowered significantly! Colors will now linger and swirl beautifully
        VELOCITY_DISSIPATION: 1.5,  // Lowered significantly! Fluid momentum keeps sweeping the colors across the page
        PRESSURE: 0.1,              // Restored pressure so the fluid actually flows
        PRESSURE_ITERATIONS: 15,    // Sweet spot between high performance and fluid accuracy
        CURL: 0,                   // Gives it that gorgeous "swirling gas" complexity
        SPLAT_RADIUS: 0.3,          // Beautiful brush size
        SPLAT_FORCE: 6000,
        SHADING: true,             // Must stay FALSE to keep it from lagging!
        COLORFUL: true,
        COLOR_UPDATE_SPEED: 3,      // Dropped to 5. Allows colors to cycle smoothly without strobing or breaking the physics loop
        PAUSED: false,
        BACK_COLOR: { r: 0, g: 0, b: 0 },
        TRANSPARENT: true,
        BLOOM: true,               // Must stay FALSE to keep it from lagging!
        BLOOM_ITERATIONS: 8,
        BLOOM_RESOLUTION: 256,
        BLOOM_INTENSITY: 0.8,
        BLOOM_THRESHOLD: 0.6,
        BLOOM_SOFT_KNEE: 0.7,
        SUNRAYS: true,             // Must stay FALSE to keep it from lagging!
        SUNRAYS_RESOLUTION: 196,
        SUNRAYS_WEIGHT: 1.0,
    });

    // Fade the canvas in after the initial splash dissipates
    setTimeout(() => {
        canvas.style.opacity = '1';
    }, 1500);

    // No event forwarding needed anymore. The simulation will 
    // natively react ONLY when the user hovers over the squircle canvas.
});
