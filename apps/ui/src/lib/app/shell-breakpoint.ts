/**
 * The shell's phone form: the top bar with its menu button, and the sidebar as a drawer. It is
 * exactly the complement of Tailwind's md (`width >= 768px`), which docks the sidebar, so no width
 * is in neither. "max-width: 767px" left a browser zoomed to 767.5 CSS px with no menu button and
 * no docked sidebar, and so no way to the places.
 */
export const PHONE_SHELL_QUERY = '(width < 768px)';
