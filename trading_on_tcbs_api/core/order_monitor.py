"""
Enhanced order monitoring with better state validation
"""
import asyncio
from typing import Dict, Set, Optional

# ANSI color codes for console output
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"

# Valid state transitions for order monitoring
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "placing": {"placed", "fully_filled"},
    "cancelling": {"fully_filled", "canceled"},
}


class OrderMonitor:
    """Enhanced order state monitoring with improved error detection"""
    
    def __init__(self, stop_event: asyncio.Event, name: str = ""):
        self.queue_alert = asyncio.Queue()
        self.stop_event = stop_event
        self.prev_state: Optional[str] = None
        self.name = name  # For debugging purposes
        self.transition_count = 0
        
    @staticmethod
    def is_valid_transition(current: str, next_state: str) -> bool:
        """
        Validate order state transitions
        
        Args:
            current: Current order state
            next_state: Next order state
            
        Returns:
            True if transition is valid
        """
        return next_state in VALID_TRANSITIONS.get(current, set())
    
    def log_transition(self, current: str, next_state: str, valid: bool) -> None:
        """Log state transitions for debugging"""
        self.transition_count += 1
        status_color = GREEN if valid else RED
        status_text = "VALID" if valid else "INVALID"
        
        print(f"{status_color}[{self.name}] Transition #{self.transition_count}: "
              f"{current} -> {next_state} ({status_text}){RESET}")

    async def alert_monitor(self, timeout: int = 2) -> None:
        """
        Monitor order alerts and detect invalid state transitions
        
        Args:
            timeout: Timeout in seconds for waiting for state changes
        """
        while not self.stop_event.is_set():
            try:
                current = await asyncio.wait_for(self.queue_alert.get(), timeout=timeout)

                if current in VALID_TRANSITIONS:
                    try:
                        if current == "cancelling":
                            if self.prev_state == "fully_filled":
                                self.prev_state = current
                            else:
                                next_state = await asyncio.wait_for(
                                    self.queue_alert.get(), timeout=timeout
                                )

                                valid = self.is_valid_transition(current, next_state)
                                self.log_transition(current, next_state, valid)
                                
                                if not valid:
                                    print(f"{RED}⛔ WARNING [{self.name}]: Invalid state transition "
                                          f"'{next_state}' after '{current}', stopping system{RESET}")
                                    self.stop_event.set()
                                else:
                                    self.prev_state = current
                        else:
                            next_state = await asyncio.wait_for(
                                self.queue_alert.get(), timeout=timeout
                            )

                            valid = self.is_valid_transition(current, next_state)
                            self.log_transition(current, next_state, valid)
                            
                            if not valid:
                                print(f"{RED}⛔ WARNING [{self.name}]: Invalid state transition "
                                      f"'{next_state}' after '{current}', stopping system{RESET}")
                                self.stop_event.set()
                            else:
                                self.prev_state = current
                                
                    except asyncio.TimeoutError:
                        print(f"{RED}⛔ WARNING [{self.name}]: No response after '{current}' "
                              f"within {timeout}s, stopping system{RESET}")
                        self.stop_event.set()
                else:
                    # Non-transition state, just update
                    self.prev_state = current
                    
            except asyncio.TimeoutError:
                # Normal timeout, continue monitoring
                continue
            except Exception as e:
                print(f"{RED}⛔ ERROR [{self.name}]: Order monitor exception: {e}{RESET}")
                self.stop_event.set()
                break
                
    def get_stats(self) -> Dict[str, int]:
        """Get monitoring statistics"""
        return {
            "transition_count": self.transition_count,
            "current_state": self.prev_state
        }
