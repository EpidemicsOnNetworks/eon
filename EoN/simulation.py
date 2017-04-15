from collections import defaultdict, Counter
import networkx as nx
import random
import heapq
import scipy


#######################
#                     #
#   Auxiliary stuff   #
#                     #
#######################

class Event(object): #for fast_SIR and fast_SIS
    r'''
    This class is used in event-driven simulations (fast_SIR and 
    fast_SIS) as an event which will be put into a priority queue.  
    
    It is sortable based on event time.
    
    An event object consists of
    self.time 
    self.function
    self.args
    
    
    When self.function is called, it is called by:
        self.function(self.time, *self.args)
    
    
        
    I wonder about whether it would be better to do this as a dict.
    
    The ability to sort based on time is why I am leaving it as a class.
    '''
    def __init__(self, time, function, args = ()):
        self.time = time
        self.function = function
        self.args = args
        

    def __lt__(self, other): #used to sort Q
        return self.time < other.time
    
class myQueue(object):
    r'''
    This class is used to store a priority queue of events
    for event-driven simulations.
    '''
    def __init__(self, tmax=float("Inf")):
        self._Q_ = []
        self.tmax=tmax
    def add(self, event):
        if event.time<self.tmax:
            heapq.heappush(self._Q_, event)
    def pop_and_run(self):
        event = heapq.heappop(self._Q_)
        event.function(event.time, *event.args)
    def __len__(self): #this will allow for something like "while Q:" 
        return len(self._Q_)

class _ListDict_(object):
    r'''
    The Gillespie algorithm with rejection-sampling will involve a step 
    that samples a random element from the set.  This is slow in Python.  
    So I'm introducing a new class based on a stack overflow answer by
    Amber (http://stackoverflow.com/users/148870/amber) 
    for a question by
    tba (http://stackoverflow.com/users/46521/tba) 
    found at
    http://stackoverflow.com/a/15993515/2966723

    Based on some limited tests (in some perhaps-atypical networks),
    the benefit appears to be pretty small.  It may be worth creating 
    this data structure in C, but I doubt it.
    '''
    
    def __init__(self):
        self.item_to_position = {}
        self.items = []

    def __len__(self):
        return len(self.items)

    def add(self, item):
        if item in self.item_to_position:
            return
        self.items.append(item)
        self.item_to_position[item] = len(self.items)-1

    def remove(self, item):
        position = self.item_to_position.pop(item)
        last_item = self.items.pop()
        if position != len(self.items):
            self.items[position] = last_item
            self.item_to_position[last_item] = position

    def choose_random(self):
        return random.choice(self.items)


def _get_rate_functions(G, tau, gamma, transmission_weight = None, 
                        recovery_weight=None):
    r'''
    INPUT:
    -----
    G : networkx Graph
        the graph disease spread on

    tau : number
        disease parameter giving edge transmission rate 
        (subject to edge scaling)

    gamma : number (default None)
        disease parameter giving typical recovery rate, 
        
    transmission_weight : string (default None)
        G.edge[u][v][transmission_weight] scales up or down the recovery 
        rate.

    recovery_weight : string       (default None)
            a label for a weight given to the nodes to scale their 
            recovery rates
                gamma_i = G.node[i][recovery_weight]*gamma
'''
    if transmission_weight is None:
        trans_rate_fxn = lambda x, y: tau
    else:
        trans_rate_fxn = lambda x, y: tau*G.edge[x][y][transmission_weight]

    if recovery_weight is None:
        rec_rate_fxn = lambda x : gamma
    else:
        rec_rate_fxn = lambda x : gamma*G.node[x][recovery_weight]


    return trans_rate_fxn, rec_rate_fxn


##########################
#                        #
#    SIMULATION CODE     #
#                        #
##########################

'''
    The code in the region below is used for stochastic simulation of 
    epidemics on networks
'''

def _simple_test_transmission_(u, v, p):
    r'''
    From figure 6.8 of Kiss, Miller, & Simon.  Please cite the book if 
    using this test_transmission function for basic_discrete_SIR_epidemic.

    This handles the simple case where transmission occurs with 
    probability p.

    :INPUTS:

    u : node
        the infected node
    v : node
        the susceptible node
    p : number between 0 and 1
        the transmission probability

    :RETURNS:

    True if u will infect v (given opportunity)
    False otherwise
    '''

    return random.random()<p


def discrete_SIR_epidemic(G, 
                test_transmission=_simple_test_transmission_, args=(), 
                initial_infecteds=None, return_full_data = False):
    #tested in test_discrete_SIR_epidemic
    r'''
    From figure 6.8 of Kiss, Miller, & Simon.  Please cite the book
    if using this algorithm.

    Return details of epidemic curve from a discrete time simulation.
    
    It assumes that individuals are infected for exactly one unit of 
    time and then recover with immunity.

    This is defined to handle a user-defined function
        test_transmission(node1,node2,*args)
    which determines whether transmission occurs.

    So elaborate rules can be created as desired by the user.

    By default it uses 
        _simple_test_transmission_
    in which case args should be entered as (p,)

    :INPUTS:

    G: NetworkX Graph (or some other structure which quacks like a 
        NetworkX Graph)
        The network on which the epidemic will be simulated.
        
    test_transmission: function(u,v,*args)
        (see below for args definition)
        A function that determines whether u transmits to v.
        It returns True if transmission happens and False otherwise.
        The default will return True with probability p, where args=(p,)

        This function can be user-defined.
        It is called like:
            test_transmission(u,v,*args)
        Note that if args is not entered, then args=(), and this call is 
        equivalent to
            test_transmission(u,v)

    args: a list or tuple
        The arguments of test_transmission coming after the nodes.  If 
        simply having transmission with probability p it should be 
        entered as 
            args=(p,)   
        [note the comma is needed to tell Python that this is really a 
        tuple]

    initial_infecteds: node or iterable of nodes (default is None)
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then a randomly chosen node is initially infected.

    return_full_data: boolean  (default False)
        Tells whether the infection and recovery times of each 
            individual node should be returned.
        It is returned in the form of two dicts, 
            infection_time and recovery_time
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time

    :RETURNS:

    if return_full_data is False:
       the scipy arrays: t, S, I, R
    else:
       the scipy arrays: t, S, I, R 
       and the dicts infection_time and recovery_time

    these arrays give all the times observed and the number in each 
    state at each time.  The dicts give times at which each node changed 
    status.
    
    :SAMPLE USE:

    ::

        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        G = nx.fast_gnp_random_graph(1000,0.002)
        t, S, I, R = EoN.discrete_SIR_epidemic(G, args = (0.6,), 
                                            initial_infecteds=range(20))
        plt.plot(t,S)
    
    
    Because this sample uses the defaults, it is equivalent to a call to 
    basic_discrete_SIR_epidemic
    '''

    if return_full_data:
        infection_time = {}
        recovery_time = {}
    
    if initial_infecteds is None:
        initial_infecteds=[random.choice(G.nodes())]
    elif G.has_node(initial_infecteds):
        initial_infecteds=[initial_infecteds]
    infecteds = initial_infecteds

    N=G.order()
    t = [0]
    S = [N-len(infecteds)]
    I = [len(infecteds)]
    R = [0]
    
    susceptible = defaultdict(lambda: True)  
    #above line is equivalent to u.susceptible=True for all nodes.
    
    for u in infecteds:
        susceptible[u] = False
    while infecteds:
        new_infecteds = []
        for u in infecteds:
            for v in G.neighbors(u):
                if susceptible[v] and test_transmission(u, v, *args):
                    new_infecteds.append(v)
                    susceptible[v] = False
            if return_full_data:
                infection_time[u] = t[-1]
                recovery_time[u] = t[-1]+1
        infecteds = new_infecteds
        R.append(R[-1]+I[-1])
        I.append(len(infecteds))
        S.append(S[-1]-I[-1])
        t.append(t[-1]+1)
    if not return_full_data:
        return scipy.array(t), scipy.array(S), scipy.array(I), \
               scipy.array(R)
    else:
        return scipy.array(t), scipy.array(S), scipy.array(I), \
                scipy.array(R), infection_time, recovery_time



def basic_discrete_SIR_epidemic(G, p, initial_infecteds=None, 
                                return_full_data = False):
    #tested in test_basic_discrete_SIR_epidemic   
    r'''
    From figure 6.8 of Kiss, Miller, & Simon.  Please cite the book if 
    using this algorithm.

    Does a simulation of the simple case of all nodes transmitting
    with probability p independently to each neighbor and then
    recovering.

    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    p : number
        transmission probability
    initial_infecteds: node or iterable of nodes  (default None)
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then a randomly chosen node is initially infected.
    return_full_data: boolean (default False)
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, 
            infection_time and recovery_time
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time

    :RETURNS:

    if return_full_data is False:
        the scipy arrays: t, S, I, R
    else:
        the scipy arrays: t, S, I, R 
        and the dicts infection_time and recovery_time

    these scipy arrays give all the times observed and the number in 
    each state at each time.  The dicts give times at which each node 
    changed status.
    
    :SAMPLE USE:

    ::


        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        G = nx.fast_gnp_random_graph(1000,0.002)
        t, S, I, R = EoN.basic_discrete_SIR_epidemic(G, 0.6)
        plt.plot(t,S)
    
    
    This sample may be boring if the randomly chosen initial infection
    doesn't trigger an epidemic.

'''

    return discrete_SIR_epidemic(G, _simple_test_transmission_, (p,), 
                                    initial_infecteds, return_full_data)


def percolate_network(G, p):
    #tested indirectly in test_basic_discrete_SIR_epidemic   

    r'''From figure 6.10 of Kiss, Miller, & Simon.  Please cite the book
    if using this algorithm.

    Performs bond percolation on the network G, keeping edges with 
    probability p

    :INPUTS:

    G : NetworkX Graph
    p : number between 0 and 1
        the probability of keeping edge

    :RETURNS:

    H : NetworkX Graph
        A network with same nodes as G, but with each edge retained 
        independently with probability p.
        
    :SAMPLE USE:

    ::


        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        G = nx.fast_gnp_random_graph(1000,0.002)
        H = EoN.percolate_network(G, 0.6)

        #H is now a graph with 60% of the edges of G
'''

    H = nx.Graph()
    H.add_nodes_from(G.nodes())
    for edge in G.edges_iter():
        if random.random()<p:
            H.add_edge(*edge)
    return H

def _edge_exists_(u, v, H):
    r'''From figure 6.10 of Kiss, Miller, & Simon.  Please cite the book
    if using this algorithm.

    Tests whether H has an edge from u to v.

    :INPUTS:

    u : node
    v : node
    H : graph

    RETURNS  H.has_edge(u,v)
    -------
    True : if H has the edge
    False : if H does not have the edge
    '''
    return H.has_edge(u,v)

def percolation_based_discrete_SIR_epidemic(G, p, 
                                            initial_infecteds=None, 
                                            return_full_data = False):
    #tested in test_basic_discrete_SIR_epidemic   
    r'''From figure 6.10 of Kiss, Miller, & Simon.  Please cite the book
    if using this algorithm.

    
    The simple case of all nodes transmitting with probability p 
    independently to each neighbor and then recovering, but using a 
    percolation-based approach.  
    
    See basic_discrete_SIR_epidemic which should produce equivalent 
    outputs.  
    
    That algorithm will be faster than this one.  
    
    The value of this function is that by performing many simulations we 
    can see that the outputs of the two are equivalent.  
    
    This algorithm leads to a better understanding of the theory.


    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    p : number
        transmission probability
    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then a randomly chosen node is initially infected.
    return_full_data: boolean
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, 
             infection_time and recovery_time
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time

    :RETURNS:

    if return_full_data is False:
        the lists: t, S, I, R
    else:
        the lists: t, S, I, R 
        and the dicts infection_time and recovery_time

    these lists give all the times observed and the number in each state 
        at each time.  
    The dicts give times at which each node changed status.
    
    :SAMPLE USE:

    ::

        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        G = nx.fast_gnp_random_graph(1000,0.002)
        t, S, I, R = EoN.percolation_based_discrete_SIR_epidemic(G, p)
        plt.plot(t,S)
    
    This is equivalent to basic_discrete_epidemic (but many simulations
    may be needed before it's clear, since these are stochastic)

'''

    if initial_infecteds is None:
        initial_infecteds=[random.choice(G.nodes())]
    elif G.has_node(initial_infecteds):
        initial_infecteds=[initial_infecteds]
    H = percolate_network(G, p)
    return discrete_SIR_epidemic(H, _edge_exists_, [H], initial_infecteds, 
                                    return_full_data)


def estimate_SIR_prob_size(G, p):
    #tested in test_estimate_SIR_prob_size
    r'''From figure 6.12 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    Provies an estimate of epidemic probability and size assuming a 
    fixed transmission probability p.  
    
    The estimate is found by performing bond percolation and then 
    finding the largest connected component in the remaining network.  
    
    This assumes that there is a single giant component above threshold.  

    It will not be an appropriate measure if the network is made up of 
    several densely connected components with very weak connections 
    between these components.

    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    p : number
        transmission probability

    :RETURNS:

    PE, AR : 
        (numbers) estimates of the probability and proportion 
           infected (attack rate) in epidemics
        (the two are equal, but each given for consistency with 
           estimate_directed_SIR_prob_size)
          
            
    :SAMPLE USE:

    ::

        import networkx as nx
        import EoN
    
        G = nx.fast_gnp_random_graph(1000,0.002)
        PE, AR = EoN.estimate_SIR_prob_size(G, 0.6)

    '''
    H = percolate_network(G, p)
    size = max((len(CC) for CC in nx.connected_components(H)))
    returnval = float(size)/G.order()
    return returnval, returnval


def directed_percolate_network(G, tau, gamma):
    #indirectly tested in test_estimate_SIR_prob_size
    r'''From figure 6.13 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.  
    
    This adds node and edge attributes in the percolated network which 
    are not at present in the figure in the book.  
    
    This option is discussed in the text.
    
    This performs directed percolation corresponding to an SIR epidemic
    assuming that transmission is at rate tau and recovery at rate 
    gamma

    :SEE ALSO:

    nonMarkov_directed_percolate_network which allows for more complex
    transmission and recovery rules.
    
    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    tau : number
        transmission rate
    gamma : number
        recovery rate

    :RETURNS:

    H : networkx DiGraph  (directed graph)
        a u->v edge exists in H if u would transmit to v if ever 
        infected.
        
        The edge has a time attribute (time_to_infect) which gives the 
        delay from infection of u until transmission occurs.
        
        Each node u has a time attribute (duration) which gives the 
        duration of its infectious period.
        
    :SAMPLE USE:


    ::

        import networkx as nx
        import EoN
        
        G = nx.fast_gnp_random_graph(1000,0.002)
        H = EoN.directed_percolate_network(G, 2, 1)

    '''
    H = nx.DiGraph()
    for u in G.nodes():
        duration = random.expovariate(gamma)
        H.add_node(u, duration = duration)
        for v in G.neighbors(u):
            time_to_infect = random.expovariate(tau)
            if time_to_infect<duration:
                H.add_edge(u,v,delay=time_to_infect)
    return H
                
def _out_component_(G, source):
    '''
    rather than following the pseudocode in figure 6.15 of 
        Kiss, Miller & Simon,
    this uses a built-in Networkx command.  

    finds the set of nodes (including source) which are reachable from 
    nodes in source.

    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    source : either a node or an iterable of nodes (set, list, tuple)
        The nodes from which the infections start.  We assume no node
        will ever have a name that is an iterable of other node names.
        It will run, but may not use source user expects.

    :RETURNS:

    reachable_nodes : set
        the set of nodes reachable from source (including source).


    Warning: if the graph G has nodes like 1, 2, 3, and (1,2,3), then a
        source of (1,2,3) is potentially ambiguous.  It will interpret
        the source as the single node (1,2,3)
    '''
    if G.has_node(source): 
        source_nodes = {source}
    else:
        source_nodes = set(source)
        
    reachable_nodes = set()

    for node in source_nodes:
        reachable_nodes = reachable_nodes.union(
                                        set(nx.descendants(G, node)))

    return reachable_nodes

def _in_component_(G, target):
    r'''
    creates the _in_component_ by basically reversing _out_component_.

    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    target : a target node (or iterable of target nodes)
        The node whose infection we are interested in.

        In principle target could be an iterable, but in this case we 
        would be finding those possible sources whose infection leads to 
        infection of at least one target, not all.

    :RETURNS:

    source_nodes : (set)
        the set of nodes (including target) from which target is 
        reachable

    :WARNING: 
        
    if the graph G has nodes like 1, 2, 3, and (1,2,3), then a
    target of (1,2,3) is potentially ambiguous.  It will interpret
    the target as the single node (1,2,3)

    '''
    if G.has_node(target):
        #potential bug if for example G has  nodes like 1, 2, 3, and 
        #(1,2,3).  Then a target of (1,2,3) is ambiguous
        target_nodes = {target}
    else:
        target_nodes = set(target)

    source_nodes = set()
    
    for node in target_nodes:
        source_nodes = source_nodes.union(set(nx.ancestors(G, node)))

    return source_nodes


def get_infected_nodes(G, tau, gamma, initial_infecteds=None):
    r'''
    From figure 6.15 of Kiss, Miller, & Simon.  Please cite the book if 
    using this algorithm

    Finds all eventually infected nodes in a simulation, assuming that 
    the intial infecteds are as given and transmission occurs with rate 
    tau and recovery with rate gamma.  
    
    Uses a percolation-based approach.

    Note that the output of this algorithm is stochastic.
    
    This code has similar run-time whether an epidemic occurs or not.
    There are much faster ways to implement an algorithm giving the same 
    output, for example by actually running an epidemic.
    
    :WARNING:
    
    why are you using this command? If it's to better understand some
    concept, that's fine.  But this command IS NOT an efficient way to
    calculate anything.  Don't do it like this.  Use one of the other
    algorithms.  Try fast_SIR, for example.
    
    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    tau : number
        transmission rate
    gamma : number
        recovery rate
    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then a randomly chosen node is initially infected.

    :RETURNS:

    infected_nodes : set
        the set of nodes infected eventually in a simulation.
        
    :SAMPLE USE:

        import networkx as nx
        import EoN
    
        G = nx.fast_gnp_random_graph(1000,0.002)
        finalR = EoN.get_infected_nodes(G, 2, 1, initial_infecteds=[0, 5])
    
    
    finds the nodes infected if 0 and 5 are the initial nodes infected
    and tau=2, gamma=1
    '''    
    if initial_infecteds is None:
        initial_infecteds=[random.choice(G.nodes())]
    elif G.has_node(initial_infecteds):
        initial_infecteds=[initial_infecteds]
    H = directed_percolate_network(G, tau, gamma)
    infected_nodes = _out_component_(G, initial_infecteds)
    return infected_nodes


def estimate_directed_SIR_prob_size(G, tau, gamma):
    #tested in test_estimate_SIR_prob_size
    '''
    From figure 6.17 of Kiss, Miller, & Simon.  Please cite the book if 
    using this algorithm
    
    Predicts probability and attack rate assuming continuous-time 
    Markovian SIR disease on network G
    
    :SEE ALSO:

    estimate_nonMarkov_SIR_prob_size which handles nonMarkovian versions

    :INPUTS:

    G : NetworkX Graph
        The network the disease will transmit through.
    tau : number
        transmission rate
    gamma : number
        recovery rate

    :RETURNS:

    PE, AR  :  numbers (between 0 and 1)
        Estimates of epidemic probability and attack rate found by 
        performing directed percolation, finding largest strongly 
        connected component and finding its in/out components.
        
    :SAMPLE USE:

    ::


        import networkx as nx
        import EoN
    
        G = nx.fast_gnp_random_graph(1000,0.003)
        PE, AR = EoN.estimate_directed_SIR_prob_size(G, 2, 1)
    
    '''
    
    H = directed_percolate_network(G, tau, gamma)
    return estimate_SIR_prob_size_from_dir_perc(H)

def estimate_SIR_prob_size_from_dir_perc(H):
    #indirectly tested in test_estimate_SIR_prob_size
    r'''
    From figure 6.17 of Kiss, Miller, & Simon.  Please cite the book if 
    using this algorithm

    :INPUTS:

    H:  directed graph (assumed to be from directed percolation on 
        previous graph G)

    :RETURNS:

    PE, AR  :  numbers
        Estimates of epidemic probability and attack rate found by 
        finding largest strongly connected component and finding in/out 
        components.
        
    :SAMPLE USE:


    ::

        import networkx as nx
        import EoN

        G = nx.fast_gnp_random_graph(1000,0.003)
        H = some_user_defined_operation_to_do_percolation(G, argument)
        PE, AR = EoN.estimate_SIR_prob_size_from_dir_perc(H)

    '''

    Hscc = max((nx.strongly_connected_components(H)), key = len)
    u = list(Hscc)[0]  #random.choice(Hscc)
    inC = _in_component_(H, u) #includes both H_{IN} and H_{SCC}
    outC = _out_component_(H, u) #includes both H_{OUT} and H_{SCC}
    N=float(H.order())
    PE = len(inC)/N
    AR = len(outC)/N
    return PE, AR
 
def estimate_nonMarkov_SIR_prob_size(G, xi, zeta, transmission):
    '''
    This is not directly described in Kiss, Miller, & Simon.  It uses
    nonMarkov_directed_percolate_network  (fig 6.18) to predict 
    epidemic probability and size.
    
    :INPUTS:

    G : NetworkX Graph
        The input graph

    xi : dict
        xi[u] gives all necessary information to determine what u's 
        infectiousness is.
    zeta : dict
        zeta[v] gives everything needed about v's susceptibility

    transmission : user-defined function
        transmission(xi[u], zeta[v]) determines whether u transmits to 
        v.

    :RETURNS:

    PE, AR  :  numbers (between 0 and 1)
        Estimates of epidemic probability and attack rate found by 
        finding largest strongly connected component and finding in/out 
        components.
        
    :SAMPLE USE:


    ::

        #mimicking the standard version with transmission rate tau
        #and recovery rate gamma
    
        import networkx as nx
        import EoN
        import random
        from collections import defaultdict
    
        G=nx.fast_gnp_random_graph(1000,0.002)
        tau = 2
        gamma = 1
    
        xi = {node:random.expovariate(gamma) for node in G.nodes()}  
        #xi[node] is duration of infection of node.
        
        zeta = defaultdict(lambda : tau) #every node has zeta=tau, so same 
                                        #transmission rate
        
        def my_transmission(infection_duration, trans_rate):
            #infect if duration is longer than time to infection.
            if infection_duration > random.expovariate(trans_rate):
                return True
            else:  
                return False
        
        PE, AR = EoN.estimate_nonMarkov_SIR_prob_size(G, xi, zeta, 
                                                        my_transmission)
            

    '''

    H = nonMarkov_directed_percolate_network(G, xi, zeta, transmission)
    return estimate_SIR_prob_size_from_dir_perc(H)
        
def nonMarkov_directed_percolate_network(G, xi, zeta, transmission):
    r'''
    From figure 6.18 of Kiss, Miller, & Simon.  
    Please cite the book if using this algorithm.

    xi and zeta are dictionaries of whatever data is needed so that 
    xi[u] and zeta[v] 
    are enough to determine the probability of a u-v transmission.

    transmissision is a user-defined function taking xi[u] and zeta[v] 
    and returning True if a transmission would occur

    :INPUTS:

    G : NetworkX Graph
        The input graph

    xi : dict
        xi[u] gives all necessary information to determine what us 
        infectiousness is.
    zeta : dict
        zeta[v] gives everything needed about vs susceptibility

    transmission : user-defined function
        transmission(xi[u], zeta[v]) determines whether u transmits to 
        v.

    :RETURNS:

    networkx DiGraph (directed graph) H.  
    Edge u,v exists in H if it will transmit given the opportunity.
    
    :SAMPLE USE:

    for now, I'm being lazy.  
    Look at the sample for estimate_nonMarkov_SIR_prob_size to infer it.
'''
    H = nx.DiGraph()
    for u in G.nodes():
        H.add_node(u)
        for v in G.neighbors(u):
            if transmission(xi[u],zeta[v]):
                H.add_edge(u,v)
    return H
    
    
    
    
### Code starting here does event-driven simulations###

def _find_trans_SIR_(Q, t, tau, source, target, status, pred_inf_time, 
                        source_rec_time, trans_event_args=()):
    r'''
    From figure A.4 of Kiss, Miller, & Simon.  Please cite the book if 
    using this algorithm.

    This involves a couple additional dicts because the pseudocode is 
    written as if the nodes are a separate class.  
    
    I find it easier to have a dict for that since I don't have control 
    over the input graph.

    Determines if a transmission from source to target will occur and if
    so puts into Q

    :INPUTS:

    Q : myQueue
        A priority queue of events
    t : number
        current time
    tau : transmission rate
    source : infected node that may transmit
    target : the possibly susceptible node that may receive a 
             transmission
    status : a dict giving the current status of every node
    pred_inf_time : a dict giving a predicted infection time of 
                    susceptible nodes (defaults to inf)
    source_rec_time :  time source will recover (a bound on when transmission
                        can occur)
    trans_event_args: tuple
                      the arguments [other than time] passed on to 
                      _process_trans_SIR_.  That is:
                      (G, node, times, S, I, R, Q, status, rec_time, 
                        pred_inf_time, trans_rate_fxn, rec_rate_fxn)

    :RETURNS:

    Nothing returned

    MODIFIES
    --------
    Q : Adds transmission events to Q
    pred_inf_time : updates predicted infection time of target.
    '''
    if status[target] == 'S':
        delay = random.expovariate(tau)
        inf_time = t + delay
        if inf_time< min(source_rec_time, pred_inf_time[target]):
            event = Event(inf_time, _process_trans_SIR_, 
                          args = trans_event_args)
            Q.add(event)
            pred_inf_time[target] = inf_time

def _process_trans_SIR_(time, G, node, times, S, I, R, Q, status, rec_time, 
                            pred_inf_time, trans_rate_fxn, 
                            rec_rate_fxn):
    r'''
    From figure A.4 of Kiss, Miller, & Simon.  Please cite the book if 
    using this algorithm.

    :INPUTS:

    G : NetworkX Graph
    time : number
         time of transmission
    node : node
         node receiving transmission.
    times : list
        list of times at which events have happened
    S, I, R : lists
        lists of numbers of nodes of each status at each time
    Q : myQueue
        the queue of events
    status : dict
        dictionary giving status of each node
    rec_time : dict
        dictionary giving recovery time of each node
    pred_inf_time : dict
        dictionary giving predicted infeciton time of nodes 
    trans_rate_fxn : function
        transmission rate trans_rate_fxn(u,v) gives transmission rate from
        u to v
    rec_rate_fxn : function
        recovery rate rec_rate_fxn(u) is recovery rate of u.
        
    :RETURNS:

    nothing returned

    MODIFIES
    --------
    status : updates status of newly infected node
    rec_time : adds recovery time for node
    times : appends time of event
    S : appends new S (reduced by 1 from last)
    I : appends new I (increased by 1)
    R : appends new R (same as last)
    Q : adds recovery and transmission events for newly infected node.
    pred_inf_time : updated for nodes that will receive transmission
                    update happens in _find_trans_SIR_

    '''
    if status[node] == 'S':  #nothing happens if already infected.
        status[node] = 'I' 
        times.append(time)
        S.append(S[-1]-1) #one less susceptible
        I.append(I[-1]+1) #one more infected
        R.append(R[-1])   #no change to recovered
        rec_time[node] = time + random.expovariate(rec_rate_fxn(node))
        
        newevent = Event(rec_time[node], _process_rec_SIR_, 
                            args = (node, times, S, I, R, status))
        Q.add(newevent) #note Q.add tests that event is before tmax
        
        for v in G.neighbors(node):
            _find_trans_SIR_(Q, time, trans_rate_fxn(node,v), node, v, status, 
                                pred_inf_time, rec_time[node],
                                trans_event_args = (G, v, times, S, I, R, Q, 
                                        status, rec_time, pred_inf_time, 
                                        trans_rate_fxn, rec_rate_fxn
                                    )
                            )
    
def _process_rec_SIR_(time, node, times, S, I, R, status):
    r'''From figure A.3 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    :INPUTS:

    event : event
         has details on node and time
    times : list
        list of times at which events have happened
    S, I, R : lists
        lists of numbers of nodes of each status at each time
    status : dict
        dictionary giving status of each node


    :RETURNS:

    Nothing

    MODIFIES
    ----------
    status : updates status of newly recovered node
    times : appends time of event
    S : appends new S (same as last)
    I : appends new I (decreased by 1)
    R : appends new R (increased by 1)
    '''
    times.append(time)
    S.append(S[-1])   #no change to number susceptible
    I.append(I[-1]-1) #one less infected
    R.append(R[-1]+1) #one more recovered
    status[node] = 'R'
    
    
def fast_SIR(G, tau, gamma, initial_infecteds = None, rho = None,
                tmax=float('Inf'), transmission_weight = None, 
                recovery_weight = None, return_full_data = False):
    #tested in test_SIR_dynamics
    r'''From figure A.3 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    fast SIR simulation assuming exponentially distributed infection and
    recovery times
    

    :INPUTS:

    G : NetworkX Graph
       The underlying network

    tau : number
       transmission rate per edge

    gamma : number
       recovery rate per node

    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then choose randomly based on rho.  If rho is also
       None, a random single node is chosen.
       If both initial_infecteds and rho are assigned, then there
       is an error.
       
    rho : number
       initial fraction infected. number is int(round(G.order()*rho))

    tmax : number   (default float('Inf'))
       maximum time after which simulation will stop.
       the default of running to infinity is okay for SIR, 
       but not for SIS.

    transmission_weight : string       (default None)
            the label for a weight given to the edges.
            transmission rate is
            G.edge[i][j][transmission_weight]*tau

    recovery_weight : string       (default None)
            a label for a weight given to the nodes to scale their 
            recovery rates
                gamma_i = G.node[i][recovery_weight]*gamma

    return_full_data: boolean
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, infection_time and 
        recovery_time.
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time

    :RETURNS:

    times, S, I, R : each a scipy array
         giving times and number in each status for corresponding time

    OR if return_full_data=True:
    times, S, I, R, infection_time, recovery_time
         first four are scipy arrays as above.  New objects are dicts
         with entries just for those nodes that were infected ever
         infection_time[node] is time of infection
         recovery_time[node] is time of recovery
    
    :SAMPLE USE:

    ::


        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        
        G = nx.configuration_model([1,5,10]*100000)
        initial_size = 10000
        gamma = 1.
        tau = 0.3
        t, S, I, R = EoN.fast_SIR(G, tau, gamma, 
                                    initial_infecteds = range(initial_size))
                                    
        plt.plot(t, I)
    '''
    
    trans_rate_fxn, rec_rate_fxn = _get_rate_functions(G, tau, gamma, 
                                                transmission_weight,
                                                recovery_weight)
    return fast_nonMarkov_SIR(G, process_trans = _process_trans_SIR_, 
                            args = (trans_rate_fxn, rec_rate_fxn), 
                            initial_infecteds=initial_infecteds, 
                            rho=rho, tmax=tmax, 
                            return_full_data=return_full_data)


def fast_nonMarkov_SIR(G, process_trans = _process_trans_SIR_, 
                        args = (), initial_infecteds = None, rho=None,
                        tmax = float('Inf'), return_full_data = False, 
                        Q=None):
    r'''
    A modification of the algorithm in figure A.3 of Kiss, Miller, & 
    Simon to allow for user-defined rules governing time of 
    transmission.  
    
    Please cite the book if using this algorithm.

    This is useful if the transmission rule is non-Markovian in time, or
    for more elaborate models.  
    
    For example if there is a mass action style transmission this can be
    incorporated into the process_trans command defined by user.

    :INPUTS:

    G : Networkx Graph
    
    process_trans : a function that handles a transmission event.
                    Called by 
                        process_trans(G, time, node, times, S, I, R, Q, 
                           status, rec_time, pred_inf_time, *args)
                    must update :   status, rec_time, times, S, I, R,
                    must also update : Q, pred_inf_time.
                    In updating these last two, it calculates the 
                       recovery time, and adds the event to Q.  
                    It then calculates predicted times of transmission 
                       to neighbors.  
                    If before current earliest prediction, it will add
                       appropriate transmission event to Q and update 
                       this prediction.
                       
    args: The final arguments going into process_trans.  
          If there is some reason to collect data about node that is 
          only calculated when transmission occurs it can modify a dict 
          or something similar that is passed as an argument.
    
    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then choose randomly based on rho.  If rho is also
       None, a random single node is chosen.
       If both initial_infecteds and rho are assigned, then there
       is an error.
       
    rho : number
       initial fraction infected. number is int(round(G.order()*rho))

    tmax : (default infinity)
        final time

    return_full_data: boolean
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, infection_time and 
        recovery_time.
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time

    
         If Q is defined:
             Then initial_infecteds consists of those nodes infected 
             **PRIOR** to t=0.  
             Those infected at t=0 will be handled by being in Q 
             already.


    Q : If user wants to predefine some events, this can be done.  This 
        can be input as a heap or as a list (it will be heapified and 
        modified).
        
        User should understand the Event class and use it.  
        
        Currently there is no guarantee this is properly supported,
        so much so that right now I'm going to force the user to edit 
        the source code before trying it.  
        
        I am reasonably confident it will work.

        When Q is input, initial_infecteds should be the of nodes in 
        I class **PRIOR** to t=0, and the events in Q must have all of 
        their recoveries.  
        
        The best way to handle nodes that should be already recovered is 
        to put them in initial_infecteds and give them a recovery event 
        at t=0.


    :RETURNS:

    times, S, I, R : each a scipy array
         giving times and number in each status for corresponding time

    OR if return_full_data=True:
    times, S, I, R, infection_time, recovery_time
         first four are scipy arrays as above.  New objects are dicts
         with entries just for those nodes that were infected ever
         infection_time[node] is time of infection
         recovery_time[node] is time of recovery

    :SAMPLE USE:

    
    '''
    if rho is not None and initial_infecteds is not None:
        raise EoNError("cannot define both initial_infecteds and rho")


    status = defaultdict(lambda: 'S') #node status defaults to 'S'
    rec_time = defaultdict(lambda: -1) #node recovery time defaults to -1
    pred_inf_time = defaultdict(lambda: float('Inf')) 
        #infection time defaults to \infty  --- this could be set to tmax, 
        #probably with a slight improvement to performance.
    
    if Q is None:
        Q = myQueue(tmax)

        if initial_infecteds is None:  #create initial infecteds list if not given
            if rho is None:
                initial_number = 1
            else:
                initial_number = int(round(G.order()*rho))
            initial_infecteds=random.sample(G.nodes(), initial_number)
        elif G.has_node(initial_infecteds):
            initial_infecteds=[initial_infecteds]
        #else it is assumed to be a list of nodes.
        
        times, S, I, R= ([0], [G.order()], [0], [0])  

        for u in initial_infecteds:
            newevent = Event(0, process_trans, args=(G, u, times, S, I, R, Q, 
                                                        status, rec_time, 
                                                        pred_inf_time
                                                    ) + args
                            )
            pred_inf_time[u] = 0
            Q.add(newevent)

    else:
        raise EoNError("inputting Q is not currently tested.\n \
                        Email joel.c.miller.research@gmail.com for help.\n \
                        I believe this code will work, but you will need to \
                        delete this message.")

        if initial_infecteds is None:
            if rho is None:
                initial_number = 0 #assuming that input Q has this 
                                   #taken care of 
            else:
                initial_number = scipy.random.binomial(G.order(),rho)
            initial_infecteds=random.sample(G.nodes(), initial_number)
        elif G.has_node(initial_infecteds):
            initial_infecteds=[initial_infecteds]

        for node in initial_infecteds:
            status[node] = 'I'
            pred_inf_time[node] = -1
        for event in Q:
            if event.action == 'transmit' and \
                            event.time<pred_inf_time[event.node]:
                pred_inf_time[event.node] = event.time
            elif event.action == 'recover':
                rec_time[event.node] = event.time
        heapq.heapify(Q)            
        times, S, I, R= ([0], [G.order()-len(initial_infecteds)], [0], [0])  
        
    
    #Note that when finally infected, pred_inf_time is correct
    #and rec_time is correct.  
    #So if return_full_data is true, these are correct

    while Q:  #all the work is done in this while loop.
        Q.pop_and_run()

    #the initial infections were treated as ordinary infection events at 
    #time 0.
    #So each initial infection added an entry at time 0 to lists.
    #We'd like to get rid these excess events.
    times = times[len(initial_infecteds):]
    S=S[len(initial_infecteds):]
    I=I[len(initial_infecteds):]
    R=R[len(initial_infecteds):]

    if not return_full_data:
        return scipy.array(times), scipy.array(S), scipy.array(I), \
               scipy.array(R) 
    else:
        #strip pred_inf_time and rec_time down to just the values for nodes 
        #that became infected
        infection_time = {node:time for (node,time) in 
                            pred_inf_time.iteritems() if status[node]!='S'}
        recovery_time = {node:time for (node,time) in 
                                rec_time.iteritems() if status[node] !='S'}
        return scipy.array(times), scipy.array(S), scipy.array(I), \
                scipy.array(R), infection_time, recovery_time


def _process_trans_SIS_(time, G, source, target, times, infection_times, S, I, Q, status, rec_time, trans_rate_fxn, rec_rate_fxn):
    r'''From figure A.6 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    :INPUTS:

    time : number
            current time
    G : NetworkX Graph
    source : node
        node causing transmission
    target : node
        node receiving transmission.
    times : list
        list of times at which events have happened
    S, I: lists
        lists of numbers of nodes of each status at each time
    Q : myQueue
        the queue of events
    status : dict
        dictionary giving status of each node
    rec_time : dict
        dictionary giving recovery time of each node
    pred_inf_time : dict
        dictionary giving predicted infeciton time of nodes 
    trans_rate_fxn : function
        transmission rate trans_rate_fxn(u,v) gives transmission rate 
        from u to v
    rec_rate_fxn : function
        recovery rate rec_rate_fxn(u) is recovery rate of u.

    :RETURNS:

    nothing returned

    MODIFIES
    --------
    status : updates status of target
    rec_time : adds recovery time for target
    times : appends time of event
    S : appends new S (reduced by 1 from last)
    I : appends new I (increased by 1)
    Q : adds recovery and transmission events for target.

    '''

    if status[target] == 'S':
        status[target] = 'I'
        I.append(I[-1]+1) #one more infected
        S.append(S[-1]-1) #one less susceptible
        times.append(time)
        rec_time[target] = time + random.expovariate(rec_rate_fxn(target))
        
        newevent = Event(rec_time[target], _process_rec_SIS_, 
                                args = (target, times, S, I, status))
        Q.add(newevent) #fails if time>tmax
        for v in G.neighbors(target): #target plays role of source here
            _find_next_trans_SIS_(Q, time, trans_rate_fxn(target, v), target, v, 
                                    status, rec_time,
                                    trans_event_args = (G, target, v, times, 
                                            infection_times, S, I, Q, status, 
                                            rec_time, trans_rate_fxn,
                                            rec_rate_fxn
                                            )
                                  )
        infection_times[target].append(time)
    if source != 'initial_condition':
        _find_next_trans_SIS_(Q, time, trans_rate_fxn(source, target), 
                                source, target, status, rec_time, 
                                trans_event_args = (G, source, target, times, 
                                            infection_times, S, I, Q, status, 
                                            rec_time, trans_rate_fxn, 
                                            rec_rate_fxn
                                            )
                             )


def _find_next_trans_SIS_(Q, time, tau, source, target, status, rec_time, 
                            trans_event_args=()):
    r'''From figure A.6 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.


    determines if a transmission from source to target will occur and if 
    so puts into Q

    :INPUTS:

    Q : myQueue
        A priority queue of events
    t : current time
    tau : transmission rate
    source : infected node that may transmit
    target : the possibly susceptible node that may receive a 
             transmission
    status : a dict giving the current status of every node
    rec_time : a dict giving the recovery time of every node that has 
               been infected.

    :RETURNS:

    nothing returned

    MODIFIES
    --------
    Q : if a transmission time is potentially valid, add the first 
        event.
        when this transmission occurs later we will consider adding 
        another event.
        note that the event includes the source, so we can later check 
        if same source will transmit again.

    Entry requirement:
    -------
    Only enter this if the source node is INFECTED.

    '''
    
    assert(status[source]=='I')
    if rec_time[target]<rec_time[source]: 
        #if target is susceptible, then rec_time[target]<time
        transmission_time = max(time, rec_time[target]) \
                            + random.expovariate(tau)
        if transmission_time < rec_time[source]:
            newEvent = Event(transmission_time, _process_trans_SIS_, 
                                args = trans_event_args
                            )
            Q.add(newEvent) #note Q checks that it's before tmax

 
def _process_rec_SIS_(time, node, times, S, I, status):
    r'''From figure A.6 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    '''

    times.append(time)
    S.append(S[-1]+1)   #no change to number susceptible
    I.append(I[-1]-1) #one less infected
    status[node] = 'S'

def fast_SIS(G, tau, gamma, initial_infecteds=None, rho = None, tmax=100, 
                transmission_weight = None, recovery_weight = None, 
                return_full_data = False):
    r'''From figure A.5 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    :INPUTS:
    
    G : NetworkX Graph
       The underlying network

    tau : number
       transmission rate per edge

    gamma : number
       recovery rate per node

    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then choose randomly based on rho.  If rho is also
       None, a random single node is chosen.
       If both initial_infecteds and rho are assigned, then there
       is an error.
       
    rho : number
       initial fraction infected. number is int(round(G.order()*rho))
       
    tmax : number
        stop time

    transmission_weight : string       (default None)
            the label for a weight given to the edges.
            transmission rate is
            G.edge[i][j][transmission_weight]*tau

    recovery_weight : string       (default None)
            a label for a weight given to the nodes to scale their 
            recovery rates
                gamma_i = G.node[i][recovery_weight]*gamma
    
    return_full_data: boolean
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, infection_time and 
        recovery_time.
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time.

    :RETURNS:

    times, S, I : each a scipy array
         giving times and number in each status for corresponding time

    or if return_full_data=True:
    times, S, I, infection_time, recovery_time
         first four are scipy arrays as above.  New objects are dicts
         with entries just for those nodes that were infected ever
         infection_time[node] is a list of times of infection
         recovery_time[node] is a list of times of recovery
    
    :SAMPLE USE:

    ::


        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        
        G = nx.configuration_model([1,5,10]*100000)
        initial_size = 10000
        gamma = 1.
        tau = 0.2
        t, S, I = EoN.fast_SIS(G, tau, gamma, tmax = 10,
                                    initial_infecteds = range(initial_size))
                                    
        plt.plot(t, I)
            
    '''
    if rho is not None and initial_infecteds is not None:
        raise EoNError("cannot define both initial_infecteds and rho")
    
    trans_rate_fxn, rec_rate_fxn = _get_rate_functions(G, tau, gamma, 
                                                transmission_weight,
                                                recovery_weight)

    if initial_infecteds is None:
        if rho is None:
            initial_number = 1
        else:
            initial_number = int(round(G.order()*rho))
        initial_infecteds=random.sample(G.nodes(), initial_number)
    elif G.has_node(initial_infecteds):
        initial_infecteds=[initial_infecteds]

    times = [0]
    S = [G.order()]
    I = [0]
    Q = myQueue(tmax)
    status = defaultdict(lambda: 'S') #node status defaults to 'S'
    rec_time = defaultdict(lambda: -1) #node recovery time defaults to -1
    rec_time['initial_condition'] = 0

    infection_times = defaultdict(lambda: []) #defaults to empty list
    recovery_times = defaultdict(lambda: [])
    for u in initial_infecteds:
        newevent = Event(0, _process_trans_SIS_, 
                            args = (G, 'initial_condition', u, times, 
                                    infection_times, S, I, Q, 
                                    status, rec_time, trans_rate_fxn, 
                                    rec_rate_fxn)
                        )
        Q.add(newevent)  #fails if >tmax
        
    while Q:
        Q.pop_and_run()

    #the initial infections were treated as ordinary infection events at 
    #time 0.
    #So each initial infection added an entry at time 0 to lists.
    #We'd like to get rid these excess events.
    times = times[len(initial_infecteds):]
    S=S[len(initial_infecteds):]
    I=I[len(initial_infecteds):]

    if not return_full_data:
        return scipy.array(times), scipy.array(S), scipy.array(I)
    else:
        return scipy.array(times), scipy.array(S), scipy.array(I), \
                infection_times, recovery_times



#someday it might be nice to add a non-Markovian SIS version here




#####Now dealing with Gillespie code#####

def _Gillespie_Initialize_(G, initial_infecteds, infection_times, 
                            return_full_data, SIR = True):
    '''Initializes the network'''
    times = [0]
    S = [G.order()-len(initial_infecteds)]
    I = [len(initial_infecteds)]
    R = [0]
    status = defaultdict(lambda:'S') #by default all are susceptible
    infected = list(initial_infecteds)
    infected_neighbor_count = defaultdict(lambda:0)#
    risk_group = defaultdict(lambda:_ListDict_()) 
    for node in initial_infecteds:
        status[node]='I'
    for node in initial_infecteds:
        for neighbor in G.neighbors(node):
            if status[neighbor]=='S':
                infected_neighbor_count[neighbor] += 1
                if infected_neighbor_count[neighbor]>1:
                    risk_group[infected_neighbor_count[neighbor]-1].remove(
                                                                    neighbor)
                risk_group[infected_neighbor_count[neighbor]].add(neighbor)
    if return_full_data:
        for node in initial_infecteds:
            infection_times[node].append(0)
    if SIR:
        return times, S, I, R, status, infected, infected_neighbor_count, \
                risk_group
    else:
        return times, S, I, status, infected, infected_neighbor_count, \
                risk_group
    
def _Gillespie_Infect_(G, S, I, R, times, infected, current_time, 
                        infected_neighbor_count, risk_group, status, 
                        infection_times, return_full_data, SIR=True):
    '''
    Chooses the node to infect.

    First chooses which risk_group the node is in.  
    Then choose the node.

    An alternative which may be cleaner (not sure about faster?) is to 
    create a data type which tracks maximum risk.  
    
    Then choose a random node and do a rejection sampling step.  
    
    If rejected, then select again.  
    
    May need a very careful rejection sampling to account for repeated 
    selection.  
    
    We could probably define this as a method of the class.
    '''
    r = random.random()*sum(n*len(risk_group[n]) for n in risk_group.keys())
    for n in risk_group.keys():
        r-= n*len(risk_group[n])
        if r<0:
            break
    #we've got n now

    recipient = risk_group[n].choose_random()
        #OLD VERSION choose random element from dict
        #based on http://stackoverflow.com/a/24949742/2966723
        #question by http://stackoverflow.com/users/2237265/jamyn
        #answer by http://stackoverflow.com/users/642757/scott-ritchie
        #
        #CURRENT VERSION
        #http://stackoverflow.com/a/15993515/2966723
    assert(status[recipient]=='S')
    risk_group[n].remove(recipient)
    infected.append(recipient)
    infection_times[recipient].append(current_time)
    status[recipient]='I'
    S.append(S[-1]-1)
    I.append(I[-1]+1)
    times.append(current_time)
    if SIR:
        R.append(R[-1])

    for neighbor in G.neighbors(recipient):
        if status[neighbor]=='S':
            if infected_neighbor_count[neighbor]>0:
                risk_group[infected_neighbor_count[neighbor]].remove(neighbor)
            infected_neighbor_count[neighbor]+=1
            risk_group[infected_neighbor_count[neighbor]].add(neighbor)
    
            

def _Gillespie_Recover_SIR_(G, S, I, R, times, infected, current_time, status,
                            infected_neighbor_count, risk_group, 
                            recovery_times, return_full_data):
    r''' Changes: S, I, R, infected, times'''
    assert(I[-1]==len(infected))
    index = random.randint(0,I[-1]-1)
    infected[index], infected[-1] = infected[-1], infected[index] 
            #http://stackoverflow.com/a/14088129/2966723
    recovering_node = infected.pop()

    I.append(I[-1]-1)
    status[recovering_node]='R'
    S.append(S[-1])
    R.append(R[-1]+1)
    times.append(current_time)
    for neighbor in G.neighbors(recovering_node):
        if status[neighbor] == 'S': #neighbor susceptible, 
                                    #its risk just got smaller
            risk_group[infected_neighbor_count[neighbor]].remove(neighbor)
            infected_neighbor_count[neighbor] -= 1
            if infected_neighbor_count[neighbor]>0:
                risk_group[infected_neighbor_count[neighbor]].add(neighbor)            
    if return_full_data:
        recovery_times[recovering_node].append(current_time)

def _Gillespie_Recover_SIS_(G, S, I, times, infected, current_time, status, 
                            infected_neighbor_count, risk_group, 
                            recovery_times, return_full_data):
    r''' From figure A.5 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.
    
    :INPUTS:
    '''
    assert(I[-1]==len(infected))
    index = random.randint(0,I[-1]-1)
    infected[index], infected[-1] = infected[-1], infected[index] 
                    #http://stackoverflow.com/a/14088129/2966723
    recovering_node = infected.pop()

    I.append(I[-1]-1)
    status[recovering_node]='S'
    S.append(S[-1]+1)
    times.append(current_time)
    infected_neighbor_count[recovering_node] = 0
    for neighbor in G.neighbors(recovering_node):
	if neighbor == recovering_node:
	    continue  #Deals with selfloops
                #there is probably a good way to count the 
                #number of infected neighbors
        if status[neighbor] == 'I':
            infected_neighbor_count[recovering_node] += 1
        else: #neighbor susceptible, its risk just got smaller
            risk_group[infected_neighbor_count[neighbor]].remove(neighbor)
            infected_neighbor_count[neighbor] -= 1
            if infected_neighbor_count[neighbor]>0:
                risk_group[infected_neighbor_count[neighbor]].add(neighbor)
    if infected_neighbor_count[recovering_node]>0:
        risk_group[infected_neighbor_count[recovering_node]].add(
                                                            recovering_node)
    if return_full_data:
        recovery_times[recovering_node].append(current_time)

def Gillespie_SIR(G, tau, gamma, initial_infecteds=None, rho = None, tmax=float('Inf'), 
                    return_full_data = False):
    #tested in test_SIR_dynamics
    r'''
    From figure A.1 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.

    Assumes that the network is unweighted.  
    
    Thus the risks are quantized: equal to tau times the number of 
    infected neighbors of a node.
    
    This would not be as good if the edges were weighted, but we could 
    put the at_risk nodes into bands.
    
    The event-driven simulation is almost certainly faster in all cases, 
    and the benefit would increase if the network were weighted.  

    At present, this does not accept recovery or transmission weights.
    This is because including that will force us to sum up these weights
    more frequently rather than just counting how many exist
    which will slow the code down.  For weights, try fast_SIR
    
    :SEE ALSO:

    fast_SIR which has the same inputs but uses a different method to 
    run much faster
    
    
    
    :INPUTS:

    G : NetworkX Graph
       The underlying network
       
    tau : number
       transmission rate per edge
       
    gamma : number
       recovery rate per node
       
    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then choose randomly based on rho.  If rho is also
       None, a random single node is chosen.
       If both initial_infecteds and rho are assigned, then there
       is an error.
       
    rho : number
       initial fraction infected. number is int(round(G.order()*rho))

    tmax : number
        stop time

    return_full_data: boolean
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, infection_time and 
        recovery_time.
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time.

    :RETURNS:

    times, S, I, R : each a scipy array
         giving times and number in each status for corresponding time

    OR if return_full_data=True:
    times, S, I, R, infection_time, recovery_time
         first four are scipy arrays as above.  New objects are dicts
         with entries just for those nodes that were infected ever
         infection_time[node] is time of infection
         recovery_time[node] is time of recovery

    :SAMPLE USE:


    ::

        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        
        G = nx.configuration_model([1,5,10]*100000)
        initial_size = 10000
        gamma = 1.
        tau = 0.3
        t, S, I, R = EoN.fast_SIR(G, tau, gamma, 
                                    initial_infecteds = range(initial_size))
                                    
        plt.plot(t, I)
    
    '''

    if rho is not None and initial_infecteds is not None:
        raise EoNError("cannot define both initial_infecteds and rho")

    
    infection_times = defaultdict(lambda: []) #defaults to an empty list for each node
    recovery_times = defaultdict(lambda: [])

    tau = float(tau)  #just to avoid integer division problems.
    gamma = float(gamma)
    
    if initial_infecteds is None:
        if rho is None:
            initial_number = 1
        else:
            initial_number = int(round(G.order()*rho))
        initial_infecteds=random.sample(G.nodes(), initial_number)
    elif G.has_node(initial_infecteds):
        initial_infecteds=[initial_infecteds]

    times, S, I, R, status, infected, infected_neighbor_count, risk_group = \
                    _Gillespie_Initialize_(G, initial_infecteds, 
                                            infection_times, return_full_data)

    total_trans_rate = tau*sum(n*len(risk_group[n]) 
                                    for n in risk_group.keys())
    total_rec_rate = gamma*len(infected)
    total_rate = total_rec_rate + total_trans_rate
    next_time = times[-1] + random.expovariate(total_rate)
    while next_time<tmax and infected:
        r = random.random()*total_rate
        if r<total_rec_rate:
            #a recovery occurs
            _Gillespie_Recover_SIR_(G, S, I, R, times, infected, next_time, 
                                    status, infected_neighbor_count, 
                                    risk_group, recovery_times, 
                                    return_full_data)
            total_rec_rate = gamma*I[-1]
        else:
            #an infection occurs
            _Gillespie_Infect_(G, S, I, R, times, infected, next_time, 
                                infected_neighbor_count, risk_group, status, 
                                infection_times, return_full_data, SIR=True)
        total_trans_rate = tau*sum(n*len(risk_group[n]) 
                                    for n in risk_group.keys())
        total_rate = total_rec_rate + total_trans_rate
        if total_rate >0:  
            next_time += random.expovariate(total_rate)

    if not return_full_data:
        return scipy.array(times), scipy.array(S), scipy.array(I), \
                scipy.array(R)
    else:
        #need to change data type of infection_times and recovery_times
        infection_time = {node: L[0] for node, L in infection_times.items()}
        recovery_time = {node: L[0] for node, L in recovery_times.items()}
        return scipy.array(times), scipy.array(S), scipy.array(I), \
                scipy.array(R), infection_time, recovery_time



def Gillespie_SIS(G, tau, gamma, initial_infecteds=None, rho = None, tmax=100, 
                    return_full_data = False):
    r'''
    
    Based on figure A.1 of Kiss, Miller, & Simon.  Please cite the
    book if using this algorithm.
    
    This could be made more efficient if we divide the at_risk nodes 
    into groups based on how at risk they are. 
    
    This would not be as good if the edges were weighted, but we could 
    put the at_risk nodes into bands.

    :WARNING: 
        
    self-edges will cause this to die.  
    You can remove self-edges by G.remove_edges_from(G.selfloop_edges())

    At present, this does not accept recovery or transmission weights.
    This is because including that will force us to sum up these weights
    more frequently rather than just counting how many exist
    which will slow the code down.  For weights, try fast_SIS
    
    :SEE ALSO:

    fast_SIS which has the same inputs but uses a much faster method.
    
    
    :INPUTS:

    G : NetworkX Graph
       The underlying network

    tau : number
       transmission rate per edge

    gamma : number
       recovery rate per node

    initial_infecteds: node or iterable of nodes
       if a single node, then this node is initially infected
       if an iterable, then whole set is initially infected
       if None, then choose randomly based on rho.  If rho is also
       None, a random single node is chosen.
       If both initial_infecteds and rho are assigned, then there
       is an error.
       
    rho : number
       initial fraction infected. number is int(round(G.order()*rho))

    tmax : number
        stop time

    return_full_data: boolean
        Tells whether the infection and recovery times of each 
        individual node should be returned.  
        It is returned in the form of two dicts, infection_time and 
        recovery_time.
        infection_time[node] is the time of infection and 
        recovery_time[node] is the recovery time.
        

    :SAMPLE USE:

    ::

        import networkx as nx
        import EoN
        import matplotlib.pyplot as plt
        
        G = nx.configuration_model([1,5,10]*100000)
        initial_size = 10000
        gamma = 1.
        tau = 0.2
        t, S, I = EoN.Gillespie_SIS(G, tau, gamma, tmax = 20,
                                    initial_infecteds = range(initial_size))
                                
        plt.plot(t, I)

    '''
    if rho is not None and initial_infecteds is not None:
        raise EoNError("cannot define both initial_infecteds and rho")

    infection_times = defaultdict(lambda: []) #defaults to an empty list 
    recovery_times = defaultdict(lambda: [])  #for each node

    tau = float(tau)  #just to avoid integer division problems.
    gamma = float(gamma)
    
    if initial_infecteds is None:
        if rho is None:
            initial_number = 1
        else:
            initial_number = int(round(G.order()*rho))
        initial_infecteds=random.sample(G.nodes(), initial_number)
    elif G.has_node(initial_infecteds):
        initial_infecteds=[initial_infecteds]

    times, S, I, status, infected, infected_neighbor_count, risk_group = \
                _Gillespie_Initialize_(G, initial_infecteds,  infection_times,  
                                        return_full_data, SIR=False)
    #note that at this point times, S, and I must all be lists 
    #since we will be appending to them

    total_trans_rate = tau*sum(n*len(risk_group[n]) 
                                    for n in risk_group.keys())
    total_rec_rate = gamma*len(infected)
    total_rate = total_rec_rate + total_trans_rate
    next_time = times[-1] + random.expovariate(total_rate)
    while next_time<tmax and infected:
        r = random.random()*total_rate
        if r<total_rec_rate:
            #a recovery occurs
            _Gillespie_Recover_SIS_(G, S, I, times, infected, next_time, 
                                    status, infected_neighbor_count, 
                                    risk_group, recovery_times, 
                                    return_full_data)
            total_rec_rate = gamma*I[-1]
        else:
            #an infection occurs
            _Gillespie_Infect_(G, S, I, [], times, infected, next_time, 
                                infected_neighbor_count, risk_group, status, 
                                infection_times, return_full_data, SIR=False)
            #updates variables as needed and calculates new max_trans_rate
        total_trans_rate = tau*sum(n*len(risk_group[n]) 
                                    for n in risk_group.keys())
        total_rate = total_rec_rate + total_trans_rate
        if total_rate>0:
            next_time += random.expovariate(total_rate)
        else:  #occurs if everyone recovered
            next_time = float('Inf')
        #        print next_time, I[-1]

    if not return_full_data:
        return scipy.array(times), scipy.array(S), scipy.array(I)
    else:
        return scipy.array(times), scipy.array(S), scipy.array(I), \
                infection_times, recovery_times

