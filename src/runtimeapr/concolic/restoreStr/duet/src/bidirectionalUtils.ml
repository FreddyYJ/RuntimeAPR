open Grammar
open Exprs
open Vocab
open Generator
open Sexplib

(* Reference: Liang et al., Learning Minimal Abstractions, POPL'11 *)
(* Terms: *)
(* 	DSF: Domain-specific witness functions generating fresh specifications *)
(* DSE: Domain-specific witness functions generating existing
   specifications *)
(* Universal: Domain-agnostic witness functions generating existing
   specifications *)
(* Observation: DSFs sometimes waste resources by deducing unlikely
   subproblems. *)
(* e.g., +^{-1} tries to generate x + 1 + 1 + 1 + ... and eventually fails
   after reaching the maximum height of VSAs. *)
(* This happens in case of lack of component expressions. *)
(* Idea: For each DSF, maintain the probability of successfully deducing
   subproblems that can be eventually solved by the current set of
   components.*)
(* If a DSF fails to derive a eventually solvable subproblem, decrease the
   probability.*)
(* Otherwise, increase the probability.*)
(* If the probability becomes small enough, we conclude generating fresh
   specifications is hopeless for the operator, and turn to its DSE
   version *)
(* because DSEs only generate specs that can be satisfied the component
   expressions, they do not incur explorations of a long chain *)
(* Formulation: suppose F^-1 generates fresh specs. *)
(* 	F : A -> {0, 1} where A is a set of fresh specs generated by F^-1 and *)
(* F runs the learn procedure over them, returning 0 if a VSA is succesfully
   learned (otherwise 1) *)
(* If F succeeds, the alpha (sampling probability) of ActiveCoarsen
   increases. *)
(* If F fails, the alpha decreases. *)
(* If the alpha becomes so small that none of a fresh spec can be sampled,
   switch to DSE. *)
(* Here, the "sampling" does not actually happen. If |fresh spec| * alpha >=
   1, then use every fresh spec without actually sampling some of them. *)

(* op (string) -> float (theta) *)
let learn_rule_cache : (string, float) BatMap.t ref = ref BatMap.empty

let euler_number = 2.71828182846

let eta = 1.

let add_learn_rule_cache is_success op =
  let theta = try BatMap.find op !learn_rule_cache with _ -> 0. in
  if theta <> -1000. then
    let theta' =
      theta
      -. eta
         *. (1. -. (if is_success then 1. else 0.) -. (1. /. euler_number))
    in
    learn_rule_cache := BatMap.add op theta' !learn_rule_cache

let is_not_fresh n_sigs op =
  (* if true then true else *)
  let theta = try BatMap.find op !learn_rule_cache with _ -> 0. in
  if theta = -1000. then true
  else
    let sampling_prob = 1. /. (1. +. (euler_number ** (-1. *. theta))) in
    (* let _ = prerr_endline (Printf.sprintf "%s sampling prob: %.2f" op
       sampling_prob) in *)
    let result = float_of_int n_sigs *. sampling_prob < 1. in
    let _ =
      if result then
        (* let _ = prerr_endline (Printf.sprintf "freeze: %s" op) in *)
        learn_rule_cache := BatMap.add op (-1000.) !learn_rule_cache
    in
    result

let int_max = max_int - 1000

type signature = Exprs.const list

type state = rewrite * signature (* production rule and abstr sig *)

type operator = string

type transition = operator * state list * state

type edge = state list * state

module StateSet = BatSet.Make (struct
  type t = state

  let compare = compare
end)

module TransitionSet = BatSet.Make (struct
  type t = transition

  let compare = compare
end)

module EdgeSet = BatSet.Make (struct
  type t = state list * state

  let compare = compare
end)

let nt_of_state (nt, sg) = nt

let sig_of_state (nt, sg) = sg

let create_edge states state = (states, state)

let type_of_signature signature =
  let _ = assert (BatList.length signature > 0) in
  type_of_const (BatList.hd signature)

let string_of_sig sigature =
  BatList.fold_left (fun acc x -> acc ^ " " ^ string_of_const x) "" sigature

let string_of_state (nt, sigature) =
  Printf.sprintf "q^%s_%s"
    (Grammar.string_of_rewrite nt)
    (string_of_sig sigature)

let string_of_statelist states =
  BatList.fold_left
    (fun acc (nt, sigature) -> acc ^ "," ^ string_of_state (nt, sigature))
    "" states

let string_of_stateset states =
  StateSet.fold
    (fun (nt, sigature) acc -> acc ^ "," ^ string_of_state (nt, sigature))
    states ""

let print_afta (states, final_states, transitions) =
  prerr_endline "=== Transitions === " ;
  TransitionSet.iter
    (fun (op, states, state) ->
      prerr_endline
        (Printf.sprintf "%s(%s) ->%s%s" op
           (string_of_statelist states)
           (if StateSet.mem state final_states then " #" else " ")
           (string_of_state state) ) )
    transitions

let share_prefix : string -> string -> bool =
 fun str1 str2 ->
  if String.length str1 * String.length str2 = 0 then false
  else
    let c1 = str1.[0] in
    let c2 = str2.[0] in
    BatChar.equal c1 c2

let share_suffix str1 str2 =
  if String.length str1 * String.length str2 = 0 then false
  else
    let c1 = BatString.get (BatString.rev str1) 0 in
    let c2 = BatString.get (BatString.rev str2) 0 in
    BatChar.equal c1 c2

module BitSet = struct
  open Containers
  include CCBV

  let intset2bitset s =
    BatSet.fold (fun i acc -> set acc i ; acc) s (create ~size:32 false)
end

let intset2bitset = BitSet.intset2bitset

let int_max = max_int - 1000

type vsa =
  | Union of vsa BatSet.t
  | Join of rewrite * vsa list
  | Direct of expr
  | Empty

exception NoSolInVSA

exception VSAFound of vsa BatSet.t

exception Covered

exception LearnDTFailure

exception LearnSinglePathFailure

exception LearnForEachFailure

(* sig -> expr (<= size) *)
let get_sigs_of_size desired_sig spec
    (nt_to_sigs, nt_to_exprs, nt_sig_to_expr) nt_rule_list
    (curr_size, max_size) =
  let nt_to_sigs, nt_to_exprs, nt_sig_to_expr =
    if curr_size = 1 then
      List.fold_left
        (fun (nt_to_sigs, nt_to_exprs, nt_sig_to_expr) (nt, rule) ->
          let holes = get_holes [] rule in
          if List.length holes = 0 then
            let expr = expr_of_rewrite rule in
            let _ =
              my_prerr_endline
                (Printf.sprintf "Generated: %s" (Exprs.string_of_expr expr))
            in
            let signature = compute_signature spec expr in
            (* if (compare desired_sig signature) = 0 then *)
            (* raise (SolutionFound expr) *)
            (* else *)
            ( add_signature nt signature nt_to_sigs
            , add_expr nt (expr, 1) nt_to_exprs
            , BatMap.add (nt, signature) expr nt_sig_to_expr )
          else (nt_to_sigs, nt_to_exprs, nt_sig_to_expr) )
        (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)
        nt_rule_list
    else (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)
  in
  let rec iter size (nt_to_sigs, nt_to_exprs, nt_sig_to_expr) =
    if size >= max_size then (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)
    else
      let nt_to_sigs, nt_to_exprs, nt_sig_to_expr =
        List.fold_left
          (fun (nt_to_sigs, nt_to_exprs, nt_sig_to_expr) (nt, rule) ->
            let nt_to_sigs, nt_to_exprs, nt_sig_to_expr =
              grow nt rule
                (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)
                desired_sig spec size
            in
            (nt_to_sigs, nt_to_exprs, nt_sig_to_expr) )
          (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)
          nt_rule_list
      in
      iter (size + 1) (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)
  in
  iter curr_size (nt_to_sigs, nt_to_exprs, nt_sig_to_expr)

let rec string_of_vsa vsa =
  match vsa with
  | Union vsas ->
      string_of_set ~first:"{" ~last:"}" ~sep:" U " string_of_vsa vsas
  | Join (rule, vsa_lst) ->
      Grammar.op_of_rule rule
      ^ string_of_list ~first:"(" ~last:")" ~sep:", " string_of_vsa vsa_lst
  | Direct expr -> Exprs.string_of_expr expr
  | Empty -> ""

(* return (lowerbound, upperbound) of size of programs in vsa *)
let rec pgm_size_of_vsa vsa =
  match vsa with
  | Direct expr -> (Exprs.size_of_expr expr, Exprs.size_of_expr expr)
  | Join (_, vsa_list) ->
      let sizes = BatList.map pgm_size_of_vsa vsa_list in
      BatList.fold_left
        (fun (lb, ub) (lb', ub') -> (lb + lb', ub + ub'))
        (1, 1) sizes
  | Union vsa_set ->
      BatSet.fold
        (fun vsa' (lb, ub) ->
          let lb', ub' = pgm_size_of_vsa vsa' in
          ((if lb' < lb then lb' else lb), if ub' > ub then ub' else ub) )
        vsa_set (int_max, -int_max)
  | Empty -> (0, 0)

let rec choose_best_from_vsa vsa =
  match vsa with
  | Direct expr -> expr
  | Union vsa_set ->
      let _ = assert (not (BatSet.is_empty vsa_set)) in
      let vsa_list = BatSet.elements vsa_set in
      let vsa_list_with_size =
        List.map (fun vsa -> (pgm_size_of_vsa vsa, vsa)) vsa_list
      in
      let vsa_list_with_size =
        List.sort
          (fun ((lb1, ub1), vsa1) ((lb2, ub2), vsa2) -> lb1 - lb2)
          vsa_list_with_size
      in
      BatList.hd vsa_list_with_size |> snd |> choose_best_from_vsa
  (* choose_best_from_vsa (BatSet.choose vsa_set) *)
  | Join (rule, vsa_list) ->
      Function
        ( op_of_rule rule
        , BatList.map choose_best_from_vsa vsa_list
        , ret_type_of_op rule )
  | Empty -> raise NoSolInVSA

let covered_pts spec expr desired_sig =
  try
    let sg = Exprs.compute_signature spec expr in
    List.fold_left
      (fun pts ((const, desired_const), i) ->
        if compare const desired_const = 0 then BatSet.add i pts else pts )
      BatSet.empty
      (BatList.combine
         (BatList.combine sg desired_sig)
         (BatList.range 0 `To (List.length desired_sig - 1)) )
  with Exprs.UndefinedSemantics -> BatSet.empty

let not_covered nt_sigs desired_sig =
  let desired_sig_opt = BatList.map (fun x -> Some x) desired_sig in
  try
    let desired_sig_opt =
      BatSet.fold
        (fun nt_sig desired_sig_opt ->
          if List.for_all (fun x -> x = None) desired_sig_opt then
            raise Covered
          else
            BatList.map
              (fun (nt_const, desired_const_opt) ->
                match desired_const_opt with
                | None -> None
                | Some desired_const ->
                    if compare nt_const desired_const = 0 then None
                    else desired_const_opt )
              (BatList.combine nt_sig desired_sig_opt) )
        nt_sigs desired_sig_opt
    in
    List.fold_left
      (fun acc (x, i) -> if x = None then acc else acc @ [i])
      []
      (List.combine desired_sig_opt
         (BatList.range 0 `To (List.length desired_sig_opt - 1)) )
  with Covered -> []

let rec remove_redundant_sigs sigs desired_sig =
  BatSet.filter
    (fun sg ->
      List.exists
        (fun (const, desired_const) -> compare const desired_const = 0)
        (List.combine sg desired_sig) )
    sigs

(* l, u : signature set *)
let rec scan_coarsen (l, u) desired_sig =
  if BatSet.equal l u then u
  else
    let elem = BatSet.diff u l |> BatSet.choose in
    let u_wo_elem = BatSet.remove elem u in
    if not_covered u_wo_elem desired_sig = [] then
      scan_coarsen (l, u_wo_elem) desired_sig
    else scan_coarsen (BatSet.add elem l, u) desired_sig

(* let rec create_ite nt_sigs = *)
(* let nt_sig = BatSet.choose nt_sigs in *)
(* let nt_sigs' = BatSet.remove nt_sig nt_sigs in *)
(* let term = BatMap.find (nt, nt_sig) nt_sig_to_expr in *)
(* if (BatSet.is_empty nt_sigs') then term *)
(* else *)
(* let bool_sig = *)
(* BatList.map (fun (nt_const, desired_const) -> *)
(* CBool ((compare nt_const desired_const) = 0) *)
(* ) (BatList.combine nt_sig desired_sig) *)
(* in *)
(* let _ = *)
(* if (compare (snd !goal) desired_sig) = 0 then *)
(* begin *)
(* let _ = prerr_endline (Printf.sprintf "desired : %s" (string_of_sig
   desired_sig)) in *)
(* let _ = prerr_endline (Printf.sprintf "nt_sig : %s" (string_of_sig
   nt_sig)) in *)
(* let _ = prerr_endline (Printf.sprintf "term : %s" (Exprs.string_of_expr
   term)) in *)
(* let _ = prerr_endline (Printf.sprintf "bool_sig : %s" (string_of_sig
   bool_sig)) in *)
(* () *)
(* end *)
(* in *)
(* let pred = *)
(* learn (available_height, available_size) *)
(* (bool_nt, bool_sig) *)
(* (spec, nt_rule_list, total_sigs, nt_to_sigs, nt_sig_to_expr) *)
(* |> (fun x -> (*prerr_endline (string_of_vsa x);*) x) |>
   choose_best_from_vsa *)
(* in *)
(* let _ = *)
(* if (compare (snd !goal) desired_sig) = 0 then *)
(* begin *)
(* let _ = prerr_endline ("term: " ^ (Exprs.string_of_expr term)) in *)
(* let _ = prerr_endline ("pred: " ^ (Exprs.string_of_expr pred)) in *)
(* () *)
(* end *)
(* in *)
(* Function ("ite", [pred; term; (create_ite nt_sigs')], nt_ty) *)
(* in *)
