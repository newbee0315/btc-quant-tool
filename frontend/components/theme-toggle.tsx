"use client"

import * as React from "react"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return (
      <button
        className="relative p-2 rounded-lg bg-gray-200 dark:bg-[#2B3139] hover:bg-gray-300 dark:hover:bg-[#363C45] transition-colors"
        aria-label="Toggle theme"
      >
        <span className="sr-only">Toggle theme</span>
        <div className="h-[1.2rem] w-[1.2rem]" />
      </button>
    )
  }

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="relative p-2 rounded-lg bg-gray-200 dark:bg-[#2B3139] hover:bg-gray-300 dark:hover:bg-[#363C45] transition-colors"
      aria-label="Toggle theme"
    >
      <Sun className="h-[1.2rem] w-[1.2rem] rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0 text-yellow-500" />
      <Moon className="absolute h-[1.2rem] w-[1.2rem] rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100 top-2 left-2 text-white" />
      <span className="sr-only">Toggle theme</span>
    </button>
  )
}
