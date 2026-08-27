# SMA SpeedWire Integration

Local Home Assistant integration for SMA inverters using the Speedwire protocol.

Version `0.2.0-beta.1` keeps the three original production entities unchanged and adds optional per-phase AC, DC string, grid, temperature and inverter-status diagnostics. Production and diagnostic polling intervals are independently configurable from the Home Assistant interface.

Optional diagnostics are staggered across refreshes. Repeatedly unsupported commands are temporarily backed off, so they cannot continuously delay the original production sensors.

This is a hardware-validation beta. Optional entities are available only when the inverter returns the corresponding register.
