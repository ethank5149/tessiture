# api/routes.py
"""
Backward compatibility shim.

This module re-exports the router from api.api_router for backward compatibility.
The actual route implementation is in api/api_router.py and modular route handlers
are in api/routes/.

NOTE: This file exists for backward compatibility. New code should import directly
from api.api_router or from the specific modules in api/routes/.
"""

# Re-export router for backward compatibility
from api.api_router import router

__all__ = ["router"]
