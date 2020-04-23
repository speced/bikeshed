;;; bikeshed.el --- major mode for .bs docs  -*- lexical-binding: t; -*-

;;; Commentary:

;; This is a major mode for editing Bikeshed files. It's a derived mode
;; built on top of Jason Blevins' excellent markdown-mode.el.

;; So far, all it adds on top of `markdown-mode' is syntax highlighting
;; for several forms of Bikeshed autolinking.

;; This program and all associated files are available under the same
;; terms as Bikeshed itself, CC0.

;;; Code:

(require 'markdown-mode)

(defgroup bikeshed nil
  "Major mode for editing text files in Bikeshed format."
  :prefix "bikeshed-"
  :group 'text
  :link '(url-link "https://tabatkins.github.io/bikeshed/"))

(defgroup bikeshed-faces nil
  "Faces used in Bikeshed Mode"
  :group 'bikeshed
  :group 'faces)

(defconst bikeshed-regex-rfc2119
  (rx word-start
      (group (| "must" "must not" "required" "shall" "shall not" "should"
                "should not" "recommended" "may" "optional"))
      word-end)
  "Regular expression for matching RFC2119 terms.
Group 1 matches the term.")

(defface bikeshed-rfc2119-face
  '((t (:inherit font-lock-warning-face)))
  "Face for RFC2119 terms."
  :group 'bikeshed-faces)

(defconst bikeshed-regex-basic-autolink
  "\\(^\\|[^\\]\\)\\(\\(''\\|<[<{]\\|\\[[$=]\\|{{\\)\\([A-Za-z0-9_/() -]+\\)\\(\\$]\\|''\\|=]\\|>>\\|}[>}]\\)\\)"
  "Regular expression for matching some Bikeshed autolinks.
Group 1 matches the character before the opening characters, if any,
ensuring that it is not a backslash escape.
Group 2 matches the entire expression, including delimiters.
Groups 3 and 5 matches the opening and closing delimiters.
Group 4 matches the text inside the delimiters.")

(defface bikeshed-autolink-face
  '((t (:inherit font-lock-builtin-face)))
  "Face for autolinks."
  :group 'bikeshed-faces)

(defun bikeshed-match-basic-autolink (last)
  "Match autolink from the point to LAST."
  (when (markdown-match-inline-generic bikeshed-regex-basic-autolink last)
    (let ((begin (match-beginning 2))
          (end (match-end 2)))
      (if (or (markdown-inline-code-at-pos-p begin)
              (markdown-inline-code-at-pos-p end)
              (markdown-in-comment-p)
              (markdown-range-property-any
               begin begin 'face '(markdown-url-face
                                   markdown-plain-url-face))
              (markdown-range-property-any
               begin end 'face '(markdown-hr-face
                                 markdown-math-face)))
          (progn (goto-char (min (1+ begin) last))
                 (when (< (point) last)
                   (markdown-match-italic last)))
        (set-match-data (list (match-beginning 2) (match-end 2)
                              (match-beginning 3) (match-end 3)
                              (match-beginning 4) (match-end 4)
                              (match-beginning 5) (match-end 5)))
        t))))

(defconst bikeshed-regex-anchor-autolink
  "\\(<a>\\)\\(\\(?:.\\|\n[^\n]\\)*?\\)\\(</a>\\)"
  "Regular expression for matching <a> autolinks.
Groups 1 and 3 match the opening and closing tags.
Group 2 matches the text.")

(defconst bikeshed-regex-citation
  "\\(^\\|[^\\]\\)\\(\\(\\[\\[!?\\)\\([A-Za-z0-9#|. -]+\\)\\(\\]\\]\\)\\)"
  "Regular expression for matching some Bikeshed citations.
Group 1 matches the character before the opening characters, if any,
ensuring that it is not a backslash escape.
Group 2 matches the entire expression, including delimiters.
Groups 3 and 5 matches the opening and closing delimiters.
Group 4 matches the text inside the delimiters.")

(defface bikeshed-citation-face
  '((t (:inherit font-lock-constant-face)))
  "Face for citations."
  :group 'bikeshed-faces)

(defun bikeshed-match-citation (last)
  "Match citation from the point to LAST."
  (when (markdown-match-inline-generic bikeshed-regex-citation last)
    (let ((begin (match-beginning 2))
          (end (match-end 2)))
      (if (or (markdown-inline-code-at-pos-p begin)
              (markdown-inline-code-at-pos-p end)
              (markdown-in-comment-p)
              (markdown-range-property-any
               begin begin 'face '(markdown-url-face
                                   markdown-plain-url-face))
              (markdown-range-property-any
               begin end 'face '(markdown-hr-face
                                 markdown-math-face)))
          (progn (goto-char (min (1+ begin) last))
                 (when (< (point) last)
                   (markdown-match-italic last)))
        (set-match-data (list (match-beginning 2) (match-end 2)
                              (match-beginning 3) (match-end 3)
                              (match-beginning 4) (match-end 4)
                              (match-beginning 5) (match-end 5)))
        t))))

(defconst bikeshed-regex-dfn
  "\\(<dfn\\(?:\\s-\\(?:export\\)\\)?>\\)\\(\\(?:.\\|\n[^\n]\\)*?\\)\\(</dfn>\\)"
  "Regular expression for matching <dfn>s.
Groups 1 and 3 match the opening and closing tags.
Group 2 matches the text.")

(defface bikeshed-definition-face
  '((t (:inherit font-lock-keyword-face)))
  "Face for definitions."
  :group 'bikeshed-faces)

(defconst bikeshed-regex-var
  "\\(|\\)\\([^|\s-]*[^|]*[^|\s-]+\\)\\(|\\)"
  "Regular expression for matching |variables|.
Groups 1 and 3 match the opening and closing pipes.
Group 2 matches the variable name.")

(defface bikeshed-variable-face
  '((t (:inherit font-lock-variable-name-face)))
  "Face for definitions."
  :group 'bikeshed-faces)

(defvar bikeshed-font-lock-keywords
  `((,bikeshed-regex-anchor-autolink . ((1 markdown-markup-properties)
                                        (2 'bikeshed-autolink-face)
                                        (3 markdown-markup-properties)))
    (bikeshed-match-basic-autolink . ((1 markdown-markup-properties)
                                      (2 'bikeshed-autolink-face)
                                      (3 markdown-markup-properties)))
    (bikeshed-match-citation . ((2 'bikeshed-citation-face)))
    (,bikeshed-regex-dfn . ((1 markdown-markup-properties)
                            (2 'bikeshed-definition-face)
                            (3 markdown-markup-properties)))
    (,bikeshed-regex-rfc2119 . ((1 'bikeshed-rfc2119-face)))
    (,bikeshed-regex-var . ((1 markdown-markup-properties)
                            (2 'bikeshed-variable-face)
                            (3 markdown-markup-properties)))
    . ,markdown-mode-font-lock-keywords)
  "Syntax highlighting for Markdown files.")

;;;###autoload
(define-derived-mode bikeshed-mode gfm-mode "BS"
  "Major mode for editing Bikeshed specs.
The following keys are bound:
\\{bikeshed-mode-map}"
  :group 'bikeshed
  ;; bikeshed documents are typically not hard-wrapped
  (setq fill-column most-positive-fixnum)
  (auto-fill-mode -1)
  (visual-line-mode 1)
  ;; specs often define camelCase terms
  (subword-mode 1)
  ;; Bikeshed custom metadata keywords start with a '!'
  (setq-local markdown-regex-declarative-metadata
              "^\\(!?[[:alpha:]][[:alpha:] _-]*?\\)\\([:=][ \t]*\\)\\(.*\\)$")
  ;; font lock
  (setq font-lock-defaults
        '(bikeshed-font-lock-keywords
          nil nil nil nil
          (font-lock-multiline . t)
          (font-lock-syntactic-face-function . markdown-syntactic-face)
          (font-lock-extra-managed-props
           . (composition display invisible rear-nonsticky
                          keymap help-echo mouse-face)))))

;;;###autoload
(add-to-list 'auto-mode-alist '("\\.bs\\'" . bikeshed-mode))

(provide 'bikeshed)
;;; bikeshed.el ends here
