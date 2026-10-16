"""Vector drawing primitives; copied into each independent project generator."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)






CUTS = {'A': (1,3,5), 'B': (2,4), 'P': (1,2,3)}
PROTOCOL_EDGES = [('build','commit'),('commit','challenge'),
                  ('challenge','verify'),('verify','objects'),
                  ('objects','root'),('verify','fallback'),('fallback','commit')]


def protocol(out):
    d=Drawing((0,0,10.9,7.5))
    for name,x,y,label in [
        ('build',3.0,6.1,'build candidate'),
        ('commit',7.8,6.1,'freeze and commit'),
        ('challenge',7.8,4.6,'sample fresh challenge'),
        ('verify',3.0,4.6,'scan and admit'),
        ('objects',3.0,3.1,'flush\nimmutable objects'),
        ('root',7.8,3.1,'swing atomic root'),
        ('fallback',3.0,1.2,'empty-anchor rebuild;\nnew commit/seed')]:
        d.box(name,x,y,3.65,.9,label,dashed=(name=='fallback'),size=8.5)
    for a,b in PROTOCOL_EDGES:
        if (a,b)==('build','commit') or (a,b)==('objects','root'):
            d.edge(a,b,'e','w')
        elif (a,b)==('challenge','verify'):
            d.edge(a,b,'w','e')
        elif b=='fallback':
            d.edge(a,b,'w','w',via=((.65,4.6),(.65,1.2)))
            d.text(.85,2.25,'reject',size=8,ha='left')
        elif a=='fallback':
            d.edge(a,b,'e','n',via=((10.45,1.2),(10.45,7.05),(7.8,7.05)))
        else:
            d.edge(a,b)
    d.save(out,'protocol')


def factorization(out):
    d=Drawing((0,0,10.8,8.1))
    def equation_box(name,x,y,w,h,title,equation):
        d.box(name,x,y,w,h,'')
        for ty,label in ((y+.42,title),(y-.25,equation)):
            d.text(x,ty,label,size=8.5)
            d.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
    equation_box('r',2.65,7.2,4.7,1.55,r'$R_P(k,a)$',r'$A_k=\sum_a R_P(k,a)y_a$')
    equation_box('s',8.15,7.2,4.7,1.55,r'$S_P(k,b)$',r'$B_k=\sum_b S_P(k,b)z_b$')
    d.box('mul',5.4,5.95,.52,.52,r'$\times$',shape='circle')
    d.box('bucket',5.4,4.95,4.7,.9,'per-key product\n'+r'$x_k A_k B_k$',size=8.5)
    d.box('sigma',5.4,4.05,.52,.52,r'$\sum$',shape='circle')
    equation_box('expect',5.4,3.0,6.3,1.4,'expected join tag',r'$\sum_k x_k A_k B_k$')
    equation_box('candidate',5.4,1.1,8.6,1.65,'candidate scan',r'$\sum_{k,a,b}\widehat{J}(k,a,b)x_k y_a z_b$')
    d.edge('r','mul','s','nw');d.edge('s','mul','s','ne')
    for a,b in [('mul','bucket'),('bucket','sigma'),('sigma','expect')]:d.edge(a,b)
    d.edge('candidate','expect','n','s');d.text(6.25,2.12,'compare',size=8.5,ha='left')
    d.save(out,'factorization')


def mixed_cuts(out):
    d=Drawing((0,0,8.0,4.65))
    from matplotlib.patches import Rectangle, Circle
    rows={'A':3.3,'B':2.55,'P':1.8}
    for epoch in range(1,6):
        x=1.6+epoch*1.05
        d.text(x,4.0,str(epoch),size=9)
        for name,y in rows.items():
            d.ax.add_patch(Rectangle((x-.24,y-.24),.48,.48,fill=False,linewidth=.55))
            if epoch in CUTS[name]:
                d.ax.add_patch(Circle((x,y),.055,color='black'))
    for name,y in rows.items():d.text(1.7,y,'$'+name+'$',size=9,ha='right')
    x=1.6+3.5*1.05
    d.line([(x,4.3),(x,1.2)],dashed=True);d.text(x,.99,r'$h=3$',size=9)
    d.ax.add_patch(Circle((2.15,.4),.055,color='black'))
    d.text(2.4,.4,'included in the cut',size=8.5,ha='left')
    d.save(out,'mixed-cuts')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    out=p.parse_args().output_dir;out.mkdir(parents=True,exist_ok=True)
    protocol(out);factorization(out);mixed_cuts(out)
