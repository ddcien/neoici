if exists('g:neoici_loaded')
    finish
endif
let g:neoici_loaded = 1

function! Neoici(args)
    let l:word = empty(a:args) ? expand('<cword>') : a:args
    let l:lines = Ici(l:word)
    if empty(l:lines)
        return
    endif
    call s:show_ici(l:lines)
endfunction

function! s:ici_visible() abort
    return exists('s:ici_win') && nvim_win_is_valid(s:ici_win)
endfunction

function! s:show_ici(lines) abort
    if !exists('s:ici_buf')
        let s:ici_buf = nvim_create_buf(v:false, v:true)
        call nvim_buf_set_option(s:ici_buf, 'filetype', 'markdown.ici')
    endif

    call nvim_buf_set_option(s:ici_buf, 'modifiable', v:true)
    call nvim_buf_set_lines(s:ici_buf, 0, -1, v:true, a:lines)
    call nvim_buf_set_option(s:ici_buf, 'modifiable', v:false)

    let l:width = 0
    for l:line in a:lines
        let l:w = strdisplaywidth(l:line)
        if l:w > l:width
            let l:width = l:w
        endif
    endfor

    let l:opts = {
                \ 'relative': 'cursor',
                \ 'width': l:width + 2,
                \ 'height': len(a:lines),
                \ 'col': 0,
                \ 'row': 1,
                \ 'anchor': 'NW',
                \ 'focusable': v:true
                \}

    if s:ici_visible()
        call nvim_win_close(s:ici_win, v:true)
    endif

    let s:ici_win = nvim_open_win(s:ici_buf, v:true, opts)
    call nvim_win_set_option(s:ici_win, 'spell', v:false)
    call nvim_win_set_option(s:ici_win, 'foldenable', v:false)
endfunction

command! -nargs=* Ici :call Neoici(<q-args>)
